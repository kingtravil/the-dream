"""PAPER execution — records ladder at cutoff, simulates realistic fills."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from the_dream.decision.decide import Decision
from the_dream.execution.base import FillResult, simulate_fill
from the_dream.normalize.schema import MarketSnapshot


@dataclass
class PaperExecutor:
    fills: List[FillResult] = field(default_factory=list)

    def execute(
        self,
        race_id: str,
        runner_id: str,
        decision: Decision,
        snapshot: MarketSnapshot,
    ) -> FillResult:
        if decision.decision.value != "BET":
            result = FillResult(
                runner_id=runner_id,
                requested_stake=0.0,
                filled_stake=0.0,
                fill_price=snapshot.back_price,
                slippage=0.0,
                partial=False,
            )
            self.fills.append(result)
            return result

        result = simulate_fill(snapshot, decision.stake)
        self.fills.append(result)
        return result
