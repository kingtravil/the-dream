"""LightGBM classifier wrapper — primary signal."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from the_dream.features.registry import FEATURE_REGISTRY_V1, vectorize

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover
    lgb = None  # type: ignore


class LGBMModel:
    def __init__(self) -> None:
        self._model: Optional[object] = None
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        if lgb is None:
            self._fitted = True
            return
        train = lgb.Dataset(X, label=y)
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbosity": -1,
            "num_leaves": 31,
        }
        self._model = lgb.train(params, train, num_boost_round=50)
        self._fitted = True

    def predict_proba(self, features: Dict[str, float]) -> float:
        x = np.array([vectorize(features, FEATURE_REGISTRY_V1)])
        if self._model is not None and lgb is not None:
            return float(self._model.predict(x)[0])
        # Heuristic fallback when no trained model
        score = (
            features.get("avg_form_last_3", 0.0) * 0.3
            + features.get("jockey_win_rate", 0.0) * 0.2
            + features.get("trainer_win_rate", 0.0) * 0.2
            + features.get("track_suitability", 0.0) * 0.15
            + features.get("going_suitability", 0.0) * 0.15
        )
        return min(max(score, 0.01), 0.99)

    def predict_batch(self, feature_dicts: List[Dict[str, float]]) -> List[float]:
        return [self.predict_proba(f) for f in feature_dicts]
