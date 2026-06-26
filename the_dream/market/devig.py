"""Overround removal and favourite-longshot handling."""

from __future__ import annotations

from typing import Dict, List, Literal

from the_dream.normalize.schema import MarketSnapshot

DevigMethod = Literal["proportional", "power", "shin"]


def price_vector(snapshots: List[MarketSnapshot]) -> Dict[str, float]:
    return {s.runner_id: s.mid_price for s in snapshots if s.mid_price > 1.0}


def proportional_devig(prices: Dict[str, float]) -> Dict[str, float]:
    p_raw = {rid: 1.0 / price for rid, price in prices.items()}
    overround = sum(p_raw.values())
    if overround <= 0:
        return {}
    return {rid: p / overround for rid, p in p_raw.items()}


def power_devig(prices: Dict[str, float], k: float = 1.0) -> Dict[str, float]:
    """Power de-vig: p_i^k / sum(p_j^k). k < 1 favours longshots less."""
    p_raw = {rid: (1.0 / price) ** k for rid, price in prices.items()}
    total = sum(p_raw.values())
    if total <= 0:
        return {}
    return {rid: p / total for rid, p in p_raw.items()}


def shin_devig(prices: Dict[str, float], z: float = 0.05) -> Dict[str, float]:
    """Simplified Shin de-vig approximation."""
    p_raw = {rid: 1.0 / price for rid, price in prices.items()}
    overround = sum(p_raw.values())
    if overround <= 1.0:
        return proportional_devig(prices)
    n = len(p_raw)
    adjusted: Dict[str, float] = {}
    for rid, p in p_raw.items():
        adjusted[rid] = (p - z / n) / (1.0 - z)
    total = sum(max(0.0, v) for v in adjusted.values())
    if total <= 0:
        return proportional_devig(prices)
    return {rid: max(0.0, v) / total for rid, v in adjusted.items()}


def devig_market(
    snapshots: List[MarketSnapshot],
    method: DevigMethod = "proportional",
) -> Dict[str, float]:
    prices = price_vector(snapshots)
    if not prices:
        return {}
    if method == "power":
        return power_devig(prices)
    if method == "shin":
        return shin_devig(prices)
    return proportional_devig(prices)
