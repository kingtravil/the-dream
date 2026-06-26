"""Canonical RaceEvent / Runner / MarketSnapshot schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Runner:
    runner_id: str
    horse_id: str
    jockey: str
    trainer: str
    barrier: int
    weight_kg: float
    is_scratched: bool = False


@dataclass(frozen=True)
class RaceEvent:
    race_id: str
    track: str
    distance_m: int
    condition: str
    start_time_utc: int
    runners: List[Runner]
    region: str = "NZ"

    @property
    def active_runners(self) -> List[Runner]:
        return [r for r in self.runners if not r.is_scratched]


@dataclass(frozen=True)
class MarketSnapshot:
    runner_id: str
    back_price: float
    lay_price: float
    last_traded: float
    traded_volume: float
    ladder: List[Tuple[float, float]] = field(default_factory=list)
    timestamp_utc: int = 0

    @property
    def mid_price(self) -> float:
        if self.last_traded > 1.0:
            return self.last_traded
        if self.back_price > 1.0 and self.lay_price > 1.0:
            return (self.back_price + self.lay_price) / 2.0
        return self.back_price


@dataclass(frozen=True)
class BSPRecord:
    runner_id: str
    bsp: float


@dataclass(frozen=True)
class HumanSignal:
    runner_id: str
    rating: float
    fair_odds: float
    tags: List[str]
    timestamp_utc: int
    analyst_id: str = "unknown"
    veto: bool = False
    agrees: bool = False
    disagrees: bool = False


@dataclass(frozen=True)
class BetRecord:
    race_id: str
    runner_id: str
    p_model_entry: float
    p_market_entry: float
    price_entry: float
    ev_net: float
    confidence: float
    stake: float
    human_signal: Optional[HumanSignal]
    decision_reason: List[str]
    bsp: Optional[float] = None
    clv_prob: Optional[float] = None
    clv_pct: Optional[float] = None
    result: Optional[str] = None
    pnl_gross: Optional[float] = None
    commission_paid: Optional[float] = None
    pnl_net: Optional[float] = None
    feature_hash: str = ""
    model_version: str = ""
    code_version: str = ""
    decision: str = "NO_BET"
    strength: Optional[str] = None
    timestamp_utc: int = 0
