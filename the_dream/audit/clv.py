"""CLV vs BSP — the truth loop."""

from __future__ import annotations


def clv_probability(p_market_entry: float, bsp: float, price_entry: float | None = None) -> float:
    """
    CLV in probability space: >0 means entry price beat the close.

    Uses entry implied prob minus BSP implied prob. When price_entry is given,
    it takes precedence over p_market_entry for the entry side.
    """
    if bsp <= 1.0:
        return 0.0
    p_entry = (1.0 / price_entry) if price_entry and price_entry > 1.0 else p_market_entry
    return (1.0 / bsp) - p_entry


def clv_percentage(price_entry: float, bsp: float) -> float:
    """CLV in price space: >0 means you got longer odds than BSP (good)."""
    if price_entry <= 1.0 or bsp <= 1.0:
        return 0.0
    return (price_entry / bsp) - 1.0


def settle_pnl(
    stake: float,
    price: float,
    won: bool,
    commission: float,
) -> tuple[float, float, float]:
    """Return (pnl_gross, commission_paid, pnl_net)."""
    if not won:
        return -stake, 0.0, -stake
    gross_winnings = stake * (price - 1.0)
    commission_paid = gross_winnings * commission
    pnl_net = gross_winnings - commission_paid
    return gross_winnings, commission_paid, pnl_net
