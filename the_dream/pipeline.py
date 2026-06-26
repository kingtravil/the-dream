"""
End-to-end pipeline orchestrator.

Wires ingestion → features → model → market → edge → decide → execute → audit.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from the_dream.audit.ledger import AuditLedger
from the_dream.config import DreamConfig, OperatingMode
from the_dream.decision.decide import Decision, DecisionContext, decide, format_output
from the_dream.edge.edge import net_ev_back
from the_dream.execution import get_executor
from the_dream.features import build_race_features, decision_cutoff
from the_dream.features.registry import feature_hash
from the_dream.human.signal import apply_human_overlay, signal_for_runner
from the_dream.ingest.form import FormStore
from the_dream.market.devig import devig_market
from the_dream.model.ensemble import ProbabilityEnsemble
from the_dream.normalize.schema import HumanSignal, MarketSnapshot, RaceEvent
from the_dream.risk.exposure import RiskState, check_risk
from the_dream.risk.kelly import fractional_kelly_stake


class DreamEngine:
    """Live/paper engine — shares decide() with backtest."""

    def __init__(
        self,
        cfg: DreamConfig | None = None,
        form_store: FormStore | None = None,
    ) -> None:
        self.cfg = cfg or DreamConfig()
        self.form_store = form_store or FormStore()
        self.ensemble = ProbabilityEnsemble()
        self.ledger = AuditLedger()
        self.risk_state = RiskState(
            bankroll=self.cfg.bankroll,
            peak_bankroll=self.cfg.bankroll,
        )
        self.executor = get_executor(self.cfg)

    def evaluate_race(
        self,
        race: RaceEvent,
        snapshots: List[MarketSnapshot],
        human_signals: Optional[List[HumanSignal]] = None,
        prior_snapshots: Optional[List[MarketSnapshot]] = None,
    ) -> List[dict]:
        """Evaluate all runners; returns spec §16 output per runner."""
        signals = human_signals or []
        cutoff = decision_cutoff(race.start_time_utc, self.cfg.decision_lead_seconds)
        valid_snaps = [s for s in snapshots if s.timestamp_utc <= cutoff]

        features = build_race_features(
            race,
            valid_snaps,
            self.form_store,
            self.cfg.decision_lead_seconds,
            prior_snapshots,
        )
        ensemble_out = self.ensemble.predict_race(features)
        p_model = apply_human_overlay(
            ensemble_out.probabilities, signals, self.cfg, cutoff
        )
        p_market = devig_market(valid_snaps, self.cfg.devig_method)
        snap_by_runner = {s.runner_id: s for s in valid_snaps}

        outputs: List[dict] = []
        for runner in race.active_runners:
            rid = runner.runner_id
            if rid not in p_model or rid not in p_market:
                continue

            snap = snap_by_runner[rid]
            price = snap.mid_price
            ev = net_ev_back(p_model[rid], price, self.cfg.commission)
            proposed = fractional_kelly_stake(
                p_model[rid],
                price,
                self.risk_state.bankroll,
                self.cfg.risk.kelly_fraction,
                self.cfg.commission,
            )
            human = signal_for_runner(signals, rid, cutoff)
            risk = check_risk(
                proposed, race.race_id, rid, snap, self.risk_state, self.cfg
            )
            ctx = DecisionContext(
                runner_id=rid,
                race_id=race.race_id,
                p_model=p_model[rid],
                p_market=p_market[rid],
                price=price,
                ev_net=ev,
                confidence=ensemble_out.confidence.get(rid, 0.5),
                cfg=self.cfg,
                risk=risk,
                human=human,
                proposed_stake=proposed,
            )
            decision = decide(ctx)
            fill = self.executor.execute(race.race_id, rid, decision, snap)
            self.ledger.log_decision(
                ctx,
                decision,
                feature_hash=feature_hash(),
                model_version=self.cfg.model_version,
                code_version=self.cfg.code_version,
                timestamp_utc=cutoff,
                fill_price=fill.fill_price,
            )
            out = format_output(ctx, decision)
            outputs.append(out)
        return outputs
