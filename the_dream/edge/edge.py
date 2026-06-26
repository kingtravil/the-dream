"""Commission-adjusted EV and adjusted edge."""

from __future__ import annotations


def net_ev_back(
    p_model: float,
    price: float,
    commission: float,
) -> float:
    """
    Net EV on a $1 BACK bet, commission c on winnings.

    ev_net = p_model * b * (1 - c) - (1 - p_model)
    """
    b = price - 1.0
    if b <= 0 or not 0.0 < p_model < 1.0:
        return -1.0
    return p_model * b * (1.0 - commission) - (1.0 - p_model)


def raw_edge(p_model: float, p_market: float) -> float:
    return p_model - p_market


def adjusted_edge(
    p_model: float,
    p_market: float,
    confidence: float,
) -> float:
    return raw_edge(p_model, p_market) * confidence


def commission_adjusted_b(price: float, commission: float) -> float:
    """Effective fractional odds after commission on winnings."""
    return (price - 1.0) * (1.0 - commission)
