"""Named, versioned feature list with reproducibility hash."""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List

FEATURE_REGISTRY_V1: List[str] = [
    "avg_form_last_3",
    "avg_form_last_10",
    "days_since_run",
    "distance_change_effect",
    "track_suitability",
    "barrier_penalty",
    "weight_vs_field",
    "class_move",
    "going_suitability",
    "jockey_win_rate",
    "jockey_roi_vs_market",
    "trainer_win_rate",
    "jt_synergy",
    "trainer_first_up_pattern",
    "track_specialisation",
    "drift_velocity",
    "steam_flag",
    "liquidity_pressure",
    "back_lay_spread",
    "depth_at_top",
]

FEATURE_VERSION = "v1"


def feature_hash(feature_names: List[str] | None = None) -> str:
    names = feature_names or FEATURE_REGISTRY_V1
    payload = json.dumps({"version": FEATURE_VERSION, "features": sorted(names)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def vectorize(features: Dict[str, float], registry: List[str] | None = None) -> List[float]:
    names = registry or FEATURE_REGISTRY_V1
    return [features.get(name, 0.0) for name in names]
