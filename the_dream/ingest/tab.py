"""Best-effort TAB secondary source — optional cross-check only."""

from __future__ import annotations

from typing import Dict, List, Optional

from the_dream.normalize.schema import MarketSnapshot


class TABClient:
    """TAB odds are best-effort; system must run fully on Betfair alone."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def fetch_odds(self, race_id: str) -> List[MarketSnapshot]:
        if not self.enabled:
            return []
        raise NotImplementedError(
            "TAB has no stable public API — enable only with a licensed feed."
        )


def tote_exchange_divergence(
    betfair: Dict[str, float],
    tab: Dict[str, float],
) -> Dict[str, float]:
    """Return per-runner divergence between exchange and tote implied probs."""
    divergence: Dict[str, float] = {}
    for runner_id, bf_price in betfair.items():
        tab_price = tab.get(runner_id)
        if tab_price and tab_price > 1.0 and bf_price > 1.0:
            divergence[runner_id] = (1.0 / bf_price) - (1.0 / tab_price)
    return divergence
