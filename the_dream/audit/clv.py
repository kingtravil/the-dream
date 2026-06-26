"""CLV vs BSP — the truth loop (de-vigged probability space is primary)."""

from __future__ import annotations

from typing import Dict, List

from the_dream.market.devig import proportional_devig


def clv_prob_devig(bsp_prob: float, p_market_entry_devig: float) -> float:
    """
    PRIMARY headline metric: de-vigged probability-space CLV.

    clv_prob_devig = bsp_prob - p_market_entry_devig
    >0 means you beat the close (lower entry implied prob than BSP).
    """
    return bsp_prob - p_market_entry_devig


def clv_prob_raw(price_entry: float, bsp: float) -> float:
    """Raw implied-prob CLV: (1/bsp) - (1/price_entry). Secondary diagnostic."""
    if bsp <= 1.0 or price_entry <= 1.0:
        return 0.0
    return (1.0 / bsp) - (1.0 / price_entry)


def clv_pct(price_entry: float, bsp: float) -> float:
    """
    Display-only decimal-odds CLV: price_entry / bsp - 1.

    >0 when price_entry > bsp (you got longer odds than the close).
    Biased upward vs prob-space when entry line is noisy — not for gating.
    """
    if price_entry <= 1.0 or bsp <= 1.0:
        return 0.0
    return (price_entry / bsp) - 1.0


def devig_bsp_probs(bsp_records: List[tuple[str, float]]) -> Dict[str, float]:
    """De-vig BSP prices across a race field."""
    prices = {rid: bsp for rid, bsp in bsp_records if bsp > 1.0}
    return proportional_devig(prices)


def null_clv_samples(
    p_market_by_runner: Dict[str, float],
    bsp_probs: Dict[str, float],
) -> List[float]:
    """
    NULL baseline: prob-space CLV of backing EVERY runner (no model, no gate).

    Must average ~0 on unbiased data; if not, the measurement pipeline is broken.
    """
    return [
        clv_prob_devig(bsp_probs[rid], p_market_by_runner[rid])
        for rid in p_market_by_runner
        if rid in bsp_probs
    ]


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
