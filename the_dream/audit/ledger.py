"""Full audit trail — every decision including NO_BETs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from the_dream.audit.clv import clv_percentage, clv_probability, settle_pnl
from the_dream.decision.decide import Decision, DecisionContext
from the_dream.normalize.schema import BetRecord, HumanSignal


class AuditLedger:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self.records: List[BetRecord] = []

    def log_decision(
        self,
        ctx: DecisionContext,
        decision: Decision,
        *,
        feature_hash: str = "",
        model_version: str = "",
        code_version: str = "",
        timestamp_utc: int = 0,
        fill_price: Optional[float] = None,
    ) -> BetRecord:
        price = fill_price or ctx.price
        record = BetRecord(
            race_id=ctx.race_id,
            runner_id=ctx.runner_id,
            p_model_entry=ctx.p_model,
            p_market_entry=ctx.p_market,
            price_entry=price,
            ev_net=ctx.ev_net,
            confidence=ctx.confidence,
            stake=decision.stake,
            human_signal=ctx.human,
            decision_reason=decision.reason,
            feature_hash=feature_hash,
            model_version=model_version,
            code_version=code_version,
            decision=decision.decision.value,
            strength=decision.strength.value if decision.strength else None,
            timestamp_utc=timestamp_utc,
        )
        self.records.append(record)
        if self.path:
            self._append_to_disk(record)
        return record

    def update_with_bsp(
        self,
        runner_id: str,
        race_id: str,
        bsp: float,
    ) -> None:
        for i, rec in enumerate(self.records):
            if rec.runner_id == runner_id and rec.race_id == race_id:
                clv_p = clv_probability(rec.p_market_entry, bsp, rec.price_entry)
                clv_pc = clv_percentage(rec.price_entry, bsp)
                self.records[i] = BetRecord(
                    **{
                        **asdict(rec),
                        "bsp": bsp,
                        "clv_prob": clv_p,
                        "clv_pct": clv_pc,
                    }
                )

    def update_with_result(
        self,
        runner_id: str,
        race_id: str,
        won: bool,
        commission: float,
    ) -> None:
        for i, rec in enumerate(self.records):
            if rec.runner_id == runner_id and rec.race_id == race_id and rec.stake > 0:
                gross, comm, net = settle_pnl(rec.stake, rec.price_entry, won, commission)
                self.records[i] = BetRecord(
                    **{
                        **asdict(rec),
                        "result": "WIN" if won else "LOSE",
                        "pnl_gross": gross,
                        "commission_paid": comm,
                        "pnl_net": net,
                    }
                )

    def _append_to_disk(self, record: BetRecord) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(record), default=str) + "\n")

    def no_bet_count(self) -> int:
        return sum(1 for r in self.records if r.decision == "NO_BET")

    def bet_count(self) -> int:
        return sum(1 for r in self.records if r.decision == "BET")
