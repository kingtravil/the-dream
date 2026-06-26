"""Fractional Kelly staking on net-of-commission odds."""

from __future__ import annotations


def full_kelly_fraction(p: float, price: float, commission: float = 0.0) -> float:
    """Kelly fraction using commission-adjusted net odds."""
    b = (price - 1.0) * (1.0 - commission)
    if b <= 0:
        return 0.0
    q = 1.0 - p
    f_star = (b * p - q) / b
    return max(0.0, f_star)


def fractional_kelly_stake(
    p: float,
    price: float,
    bankroll: float,
    kelly_fraction: float,
    commission: float = 0.0,
) -> float:
    f_star = full_kelly_fraction(p, price, commission)
    stake_fraction = kelly_fraction * f_star
    return bankroll * stake_fraction
