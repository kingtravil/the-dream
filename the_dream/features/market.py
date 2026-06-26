"""Market microstructure features."""

from __future__ import annotations

from typing import Dict, List, Optional

from the_dream.normalize.schema import MarketSnapshot


def market_features(
    snapshot: MarketSnapshot,
    prior_snapshot: Optional[MarketSnapshot] = None,
) -> Dict[str, float]:
    spread = 0.0
    if snapshot.back_price > 1.0 and snapshot.lay_price > 1.0:
        spread = (snapshot.lay_price - snapshot.back_price) / snapshot.back_price

    depth_at_top = sum(size for _, size in snapshot.ladder[:3])

    drift_velocity = 0.0
    steam_flag = 0.0
    if prior_snapshot and prior_snapshot.mid_price > 1.0:
        dt = max(snapshot.timestamp_utc - prior_snapshot.timestamp_utc, 1)
        drift_velocity = (prior_snapshot.mid_price - snapshot.mid_price) / dt
        if drift_velocity > 0.001:
            steam_flag = 1.0

    liquidity_pressure = min(snapshot.traded_volume / 10_000.0, 1.0)

    return {
        "drift_velocity": drift_velocity,
        "steam_flag": steam_flag,
        "liquidity_pressure": liquidity_pressure,
        "back_lay_spread": spread,
        "depth_at_top": depth_at_top,
    }
