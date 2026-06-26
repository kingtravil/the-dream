"""Replay historical races chronologically — no forward-looking data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from the_dream.audit.ledger import AuditLedger
from the_dream.config import DreamConfig
from the_dream.decision.decide import Decision, DecisionContext, decide
from the_dream.edge.edge import net_ev_back
from the_dream.execution import get_executor
from the_dream.features import build_race_features, decision_cutoff
from the_dream.features.registry import feature_hash
from the_dream.human.signal import apply_human_overlay, signal_for_runner
from the_dream.ingest.form import FormStore
from the_dream.market.devig import devig_market
from the_dream.model.ensemble import ProbabilityEnsemble
from the_dream.normalize.schema import BSPRecord, HumanSignal, MarketSnapshot, RaceEvent
from the_dream.risk.exposure import RiskState, check_risk
from the_dream.risk.kelly import fractional_kelly_stake


@dataclass
class ReplayRace:
    race: RaceEvent
    snapshots: List[MarketSnapshot]
    bsp: List[BSPRecord]
    human_signals: List[HumanSignal] = field(default_factory=list)
    winner_id: Optional[str] = None


@dataclass
class BacktestEngine:
    cfg: DreamConfig
    form_store: FormStore
    ensemble: ProbabilityEnsemble = field(default_factory=ProbabilityEnsemble)
    ledger: AuditLedger = field(default_factory=AuditLedger)
    risk_state: RiskState = field(default_factory=lambda: RiskState(
        bankroll=10_000.0, peak_bankroll=10_000.0
    ))

    def __post_init__(self) -> None:
        self.risk_state.bankroll = self.cfg.bankroll
        self.risk_state.peak_bankroll = self.cfg.bankroll

    def decide_for_runner(
        self,
        race: RaceEvent,
        runner_id: str,
        p_model: float,
        p_market: float,
        price: float,
        confidence: float,
        snapshot: MarketSnapshot,
        human_signals: List[HumanSignal],
    ) -> Decision:
        """Backtest decision path — calls the same pure decide() as live."""
        cutoff = decision_cutoff(race.start_time_utc, self.cfg.decision_lead_seconds)
        ev = net_ev_back(p_model, price, self.cfg.commission)
        proposed = fractional_kelly_stake(
            p_model,
            price,
            self.risk_state.bankroll,
            self.cfg.risk.kelly_fraction,
            self.cfg.commission,
        )
        human = signal_for_runner(human_signals, runner_id, cutoff)
        risk = check_risk(
            proposed,
            race.race_id,
            runner_id,
            snapshot,
            self.risk_state,
            self.cfg,
        )
        ctx = DecisionContext(
            runner_id=runner_id,
            race_id=race.race_id,
            p_model=p_model,
            p_market=p_market,
            price=price,
            ev_net=ev,
            confidence=confidence,
            cfg=self.cfg,
            risk=risk,
            human=human,
            proposed_stake=proposed,
        )
        return decide(ctx)

    def replay_race(self, replay: ReplayRace) -> List[Decision]:
        race = replay.race
        cutoff = decision_cutoff(race.start_time_utc, self.cfg.decision_lead_seconds)
        valid_snaps = [s for s in replay.snapshots if s.timestamp_utc <= cutoff]

        features = build_race_features(
            race, valid_snaps, self.form_store, self.cfg.decision_lead_seconds
        )
        ensemble_out = self.ensemble.predict_race(features)
        p_model = apply_human_overlay(
            ensemble_out.probabilities,
            replay.human_signals,
            self.cfg,
            cutoff,
        )
        p_market = devig_market(valid_snaps, self.cfg.devig_method)
        snap_by_runner = {s.runner_id: s for s in valid_snaps}

        executor = get_executor(self.cfg)
        decisions: List[Decision] = []

        for runner in race.active_runners:
            rid = runner.runner_id
            if rid not in p_model or rid not in p_market:
                continue
            snap = snap_by_runner[rid]
            price = snap.mid_price
            decision = self.decide_for_runner(
                race,
                rid,
                p_model[rid],
                p_market[rid],
                price,
                ensemble_out.confidence.get(rid, 0.5),
                snap,
                replay.human_signals,
            )
            decisions.append(decision)

            ctx = DecisionContext(
                runner_id=rid,
                race_id=race.race_id,
                p_model=p_model[rid],
                p_market=p_market[rid],
                price=price,
                ev_net=net_ev_back(p_model[rid], price, self.cfg.commission),
                confidence=ensemble_out.confidence.get(rid, 0.5),
                cfg=self.cfg,
                risk=check_risk(0, race.race_id, rid, snap, self.risk_state, self.cfg),
                human=signal_for_runner(replay.human_signals, rid, cutoff),
            )
            fill = executor.execute(race.race_id, rid, decision, snap)
            self.ledger.log_decision(
                ctx,
                decision,
                feature_hash=feature_hash(),
                model_version=self.cfg.model_version,
                code_version=self.cfg.code_version,
                timestamp_utc=cutoff,
                fill_price=fill.fill_price,
            )

        bsp_map = {b.runner_id: b.bsp for b in replay.bsp}
        self.ledger.update_race_clv(race.race_id, replay.bsp)

        if replay.winner_id:
            for runner in race.active_runners:
                won = runner.runner_id == replay.winner_id
                self.ledger.update_with_result(
                    runner.runner_id,
                    race.race_id,
                    won,
                    self.cfg.commission,
                )

        return decisions

    def replay_all(self, races: List[ReplayRace]) -> AuditLedger:
        for replay in sorted(races, key=lambda r: r.race.start_time_utc):
            self.replay_race(replay)
        return self.ledger
