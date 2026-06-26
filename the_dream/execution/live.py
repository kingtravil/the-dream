"""LIVE execution — full staking with partial match handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from the_dream.decision.decide import Decision
from the_dream.execution.base import FillResult, simulate_fill
from the_dream.ingest.betfair import BetfairRESTClient
from the_dream.normalize.schema import MarketSnapshot


@dataclass
class LiveExecutor:
    client: Optional[BetfairRESTClient] = None
    fills: List[FillResult] = field(default_factory=list)

    def execute(
        self,
        race_id: str,
        runner_id: str,
        decision: Decision,
        snapshot: MarketSnapshot,
    ) -> FillResult:
        if decision.decision.value != "BET":
            return FillResult(
                runner_id=runner_id,
                requested_stake=0.0,
                filled_stake=0.0,
                fill_price=snapshot.back_price,
                slippage=0.0,
                partial=False,
            )

        # Placeholder until Betfair placeOrders is wired
        if self.client is None:
            result = simulate_fill(snapshot, decision.stake, market_impact_pct=0.015)
        else:
            result = simulate_fill(snapshot, decision.stake, market_impact_pct=0.015)

        self.fills.append(result)
        return result
