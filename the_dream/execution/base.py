"""Execution interface — paper / micro / live share the same contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from the_dream.decision.decide import Decision
from the_dream.normalize.schema import MarketSnapshot


@dataclass(frozen=True)
class FillResult:
    runner_id: str
    requested_stake: float
    filled_stake: float
    fill_price: float
    slippage: float
    partial: bool


class Executor(Protocol):
    def execute(
        self,
        race_id: str,
        runner_id: str,
        decision: Decision,
        snapshot: MarketSnapshot,
    ) -> FillResult: ...


def simulate_fill(
    snapshot: MarketSnapshot,
    stake: float,
    market_impact_pct: float = 0.01,
) -> FillResult:
    """
    Honest paper fill: best available minus market impact for size.
    Allows partial fills when depth is insufficient.
    """
    if stake <= 0:
        return FillResult(
            runner_id=snapshot.runner_id,
            requested_stake=0.0,
            filled_stake=0.0,
            fill_price=snapshot.back_price,
            slippage=0.0,
            partial=False,
        )

    available = sum(size for _, size in snapshot.ladder) if snapshot.ladder else stake
    filled = min(stake, available)
    partial = filled < stake

    impact = market_impact_pct * (filled / max(available, 1.0))
    fill_price = snapshot.back_price * (1.0 + impact)
    slippage = (fill_price - snapshot.back_price) / max(snapshot.back_price, 1.0)

    return FillResult(
        runner_id=snapshot.runner_id,
        requested_stake=stake,
        filled_stake=filled,
        fill_price=fill_price,
        slippage=slippage,
        partial=partial,
    )
