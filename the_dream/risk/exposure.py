"""Exposure caps, liquidity filter, drawdown circuit-breaker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from the_dream.config import DreamConfig, RiskLimits
from the_dream.normalize.schema import MarketSnapshot


@dataclass
class RiskState:
    bankroll: float
    peak_bankroll: float
    race_exposure: Dict[str, float] = field(default_factory=dict)
    global_exposure: float = 0.0
    active_stakes: Dict[str, float] = field(default_factory=dict)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_bankroll <= 0:
            return 0.0
        return (self.peak_bankroll - self.bankroll) / self.peak_bankroll


@dataclass(frozen=True)
class RiskCheck:
    passes: bool
    reason: str = ""
    adjusted_stake: float = 0.0


def check_risk(
    stake: float,
    race_id: str,
    runner_id: str,
    snapshot: Optional[MarketSnapshot],
    state: RiskState,
    cfg: DreamConfig,
) -> RiskCheck:
    limits: RiskLimits = cfg.risk

    if state.drawdown_pct >= limits.drawdown_circuit_breaker_pct:
        return RiskCheck(False, "drawdown circuit-breaker triggered")

    max_stake = state.bankroll * limits.max_stake_pct_bankroll
    adjusted = min(stake, max_stake)

    race_exp = state.race_exposure.get(race_id, 0.0) + adjusted
    if race_exp > state.bankroll * limits.max_race_exposure_pct:
        return RiskCheck(False, "max race exposure exceeded")

    if state.global_exposure + adjusted > state.bankroll * limits.max_global_exposure_pct:
        return RiskCheck(False, "max global exposure exceeded")

    if snapshot and snapshot.ladder:
        depth = sum(size for _, size in snapshot.ladder[:3])
        max_liquidity_stake = depth * limits.max_depth_pct
        if depth > 0 and adjusted > max_liquidity_stake:
            adjusted = max_liquidity_stake

    if adjusted <= 0:
        return RiskCheck(False, "stake reduced to zero by limits")

    return RiskCheck(True, "", adjusted)


def scale_concurrent_stakes(
    stakes: Dict[str, float],
    bankroll: float,
    max_global_pct: float,
) -> Dict[str, float]:
    """Scale down simultaneous Kelly bets to respect global cap."""
    total = sum(stakes.values())
    cap = bankroll * max_global_pct
    if total <= cap or total <= 0:
        return stakes
    scale = cap / total
    return {k: v * scale for k, v in stakes.items()}
