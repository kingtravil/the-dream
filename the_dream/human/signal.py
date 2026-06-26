"""Bounded human expert overlay — max ±15%, logged, never silent."""

from __future__ import annotations

from typing import Dict, List, Optional

from the_dream.config import DreamConfig
from the_dream.model.logit import softmax
from the_dream.normalize.schema import HumanSignal


def apply_human_overlay(
    p_model: Dict[str, float],
    signals: List[HumanSignal],
    cfg: DreamConfig,
    decision_cutoff_utc: int,
) -> Dict[str, float]:
    """Apply bounded nudge before re-normalization."""
    adjusted = dict(p_model)
    max_nudge = cfg.human_overlay_max_pct

    for signal in signals:
        if signal.timestamp_utc > decision_cutoff_utc:
            continue
        if signal.runner_id not in adjusted:
            continue
        nudge = (signal.rating - 0.5) * 2.0 * max_nudge
        nudge = max(-max_nudge, min(max_nudge, nudge))
        adjusted[signal.runner_id] = adjusted[signal.runner_id] * (1.0 + nudge)

    return softmax(adjusted)


def signal_for_runner(
    signals: List[HumanSignal],
    runner_id: str,
    decision_cutoff_utc: int,
) -> Optional[HumanSignal]:
    valid = [
        s
        for s in signals
        if s.runner_id == runner_id and s.timestamp_utc <= decision_cutoff_utc
    ]
    if not valid:
        return None
    return max(valid, key=lambda s: s.timestamp_utc)
