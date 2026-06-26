"""Shadow CLV harness — decide() runs, stake nothing, measure CLV vs BSP."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from the_dream.audit.clv import devig_bsp_probs, null_clv_samples
from the_dream.audit.ledger import AuditLedger
from the_dream.backtest.metrics import CLVReport, build_clv_report, write_clv_report
from the_dream.config import DreamConfig
from the_dream.decision.decide import Decision, DecisionContext, decide
from the_dream.edge.edge import net_ev_back
from the_dream.features import build_race_features, decision_cutoff, validate_snapshots_at_cutoff
from the_dream.features.registry import feature_hash
from the_dream.human.signal import apply_human_overlay, signal_for_runner
from the_dream.ingest.form import FormStore
from the_dream.ingest.historical import HistoricalReplayRace, iter_replay_races
from the_dream.market.devig import devig_market
from the_dream.model.ensemble import ProbabilityEnsemble
from the_dream.normalize.schema import HumanSignal
from the_dream.risk.exposure import RiskCheck, RiskState, check_risk
from the_dream.risk.kelly import fractional_kelly_stake


@dataclass
class ShadowCLVHarness:
    cfg: DreamConfig
    form_store: FormStore = field(default_factory=FormStore)
    ensemble: ProbabilityEnsemble = field(default_factory=ProbabilityEnsemble)
    ledger: AuditLedger = field(default_factory=AuditLedger)
    risk_state: RiskState = field(default_factory=lambda: RiskState(
        bankroll=10_000.0, peak_bankroll=10_000.0
    ))
    null_clv_all: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.risk_state.bankroll = self.cfg.bankroll
        self.risk_state.peak_bankroll = self.cfg.bankroll

    def _record_null_baseline(
        self,
        p_market: Dict[str, float],
        bsp_probs: Dict[str, float],
    ) -> None:
        self.null_clv_all.extend(null_clv_samples(p_market, bsp_probs))

    def shadow_race(self, replay: HistoricalReplayRace) -> List[Decision]:
        race = replay.race
        cutoff = replay.decision_cutoff_utc or decision_cutoff(
            race.start_time_utc, self.cfg.decision_lead_seconds
        )
        validate_snapshots_at_cutoff(replay.snapshots, cutoff)

        features = build_race_features(
            race, replay.snapshots, self.form_store, self.cfg.decision_lead_seconds
        )
        ensemble_out = self.ensemble.predict_race(features)
        p_model = apply_human_overlay(
            ensemble_out.probabilities, [], self.cfg, cutoff
        )
        p_market = devig_market(replay.snapshots, self.cfg.devig_method)
        bsp_probs = devig_bsp_probs([(b.runner_id, b.bsp) for b in replay.bsp])
        self._record_null_baseline(p_market, bsp_probs)

        snap_by_runner = {s.runner_id: s for s in replay.snapshots}
        decisions: List[Decision] = []

        for runner in race.active_runners:
            rid = runner.runner_id
            if rid not in p_model or rid not in p_market or rid not in snap_by_runner:
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
                human=None,
                proposed_stake=proposed,
            )
            decision = decide(ctx)
            decisions.append(decision)

            self.ledger.log_decision(
                ctx,
                decision,
                feature_hash=feature_hash(),
                model_version=self.cfg.model_version,
                code_version=self.cfg.code_version,
                timestamp_utc=cutoff,
                fill_price=price,
                shadow=True,
            )

        self.ledger.update_race_clv(race.race_id, replay.bsp)
        return decisions

    def run_paths(self, paths: List[Path]) -> CLVReport:
        for replay in iter_replay_races(paths, self.cfg):
            self.shadow_race(replay)
        report = build_clv_report(self.ledger, self.null_clv_all)
        return report

    def run_races(self, races: List[HistoricalReplayRace]) -> CLVReport:
        for replay in sorted(races, key=lambda r: r.race.start_time_utc):
            self.shadow_race(replay)
        return build_clv_report(self.ledger, self.null_clv_all)
