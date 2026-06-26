"""Full audit trail — every decision including NO_BETs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from the_dream.audit.clv import clv_pct, clv_prob_devig, clv_prob_raw, devig_bsp_probs
from the_dream.audit.clv import settle_pnl
from the_dream.decision.decide import Decision, DecisionContext
from the_dream.normalize.schema import BetRecord, BSPRecord, HumanSignal


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
        shadow: bool = False,
    ) -> BetRecord:
        price = fill_price or ctx.price
        stake = 0.0 if shadow else decision.stake
        record = BetRecord(
            race_id=ctx.race_id,
            runner_id=ctx.runner_id,
            p_model_entry=ctx.p_model,
            p_market_entry=ctx.p_market,
            price_entry=price,
            ev_net=ctx.ev_net,
            confidence=ctx.confidence,
            stake=stake,
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

    def update_race_clv(
        self,
        race_id: str,
        bsp_records: List[BSPRecord],
    ) -> None:
        """Compute de-vigged prob-space CLV for all records in a race."""
        bsp_probs = devig_bsp_probs([(b.runner_id, b.bsp) for b in bsp_records])
        bsp_by_runner = {b.runner_id: b.bsp for b in bsp_records}

        for i, rec in enumerate(self.records):
            if rec.race_id != race_id:
                continue
            rid = rec.runner_id
            bsp = bsp_by_runner.get(rid)
            bsp_prob = bsp_probs.get(rid)
            if bsp is None or bsp_prob is None:
                continue
            self.records[i] = BetRecord(
                **{
                    **asdict(rec),
                    "bsp": bsp,
                    "bsp_prob": bsp_prob,
                    "clv_prob": clv_prob_devig(bsp_prob, rec.p_market_entry),
                    "clv_prob_raw": clv_prob_raw(rec.price_entry, bsp),
                    "clv_pct": clv_pct(rec.price_entry, bsp),
                }
            )

    def update_with_bsp(
        self,
        runner_id: str,
        race_id: str,
        bsp: float,
    ) -> None:
        """Legacy single-runner update — prefer update_race_clv for correct de-vig."""
        self.update_race_clv(race_id, [BSPRecord(runner_id=runner_id, bsp=bsp)])

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

    def would_be_bets(self) -> List[BetRecord]:
        """Records where decide() returned BET (stake may be 0 in shadow mode)."""
        return [r for r in self.records if r.decision == "BET"]
