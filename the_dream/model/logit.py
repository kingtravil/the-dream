"""Conditional logit / Harville-style race structure layer."""

from __future__ import annotations

import math
from typing import Dict, List


def softmax(scores: Dict[str, float], temperature: float = 1.0) -> Dict[str, float]:
    if not scores:
        return {}
    max_s = max(scores.values())
    exp_scores = {
        rid: math.exp((s - max_s) / max(temperature, 1e-6)) for rid, s in scores.items()
    }
    total = sum(exp_scores.values())
    if total <= 0:
        n = len(scores)
        return {rid: 1.0 / n for rid in scores}
    return {rid: v / total for rid, v in exp_scores.items()}


class ConditionalLogit:
    """Race-normalized probabilities via softmax over utility scores."""

    def __init__(self, temperature: float = 1.0) -> None:
        self.temperature = temperature

    def predict_race(
        self,
        utilities: Dict[str, float],
    ) -> Dict[str, float]:
        return softmax(utilities, self.temperature)

    def utilities_from_features(
        self,
        features_by_runner: Dict[str, Dict[str, float]],
    ) -> Dict[str, float]:
        utilities: Dict[str, float] = {}
        for rid, feats in features_by_runner.items():
            utilities[rid] = (
                feats.get("avg_form_last_3", 0.0) * 2.0
                + feats.get("barrier_penalty", 0.0) * 5.0
                + feats.get("weight_vs_field", 0.0) * 3.0
                + feats.get("jt_synergy", 0.0) * 1.5
            )
        return utilities
