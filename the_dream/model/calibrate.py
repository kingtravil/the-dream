"""Isotonic / Platt calibration on held-out time-forward split."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

try:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
except ImportError:  # pragma: no cover
    IsotonicRegression = None  # type: ignore
    LogisticRegression = None  # type: ignore


class Calibrator:
    def __init__(self, method: str = "isotonic") -> None:
        self.method = method
        self._model: Optional[object] = None
        self._fitted = False

    def fit(self, probs: np.ndarray, outcomes: np.ndarray) -> None:
        if len(probs) < 10:
            self._fitted = False
            return
        if self.method == "platt" and LogisticRegression is not None:
            self._model = LogisticRegression()
            self._model.fit(probs.reshape(-1, 1), outcomes)
        elif IsotonicRegression is not None:
            self._model = IsotonicRegression(out_of_bounds="clip")
            self._model.fit(probs, outcomes)
        self._fitted = True

    def calibrate(self, prob: float) -> float:
        if not self._fitted or self._model is None:
            return prob
        if self.method == "platt":
            return float(self._model.predict_proba(np.array([[prob]]))[0, 1])
        return float(self._model.predict(np.array([prob]))[0])

    def calibrate_batch(self, probs: Dict[str, float]) -> Dict[str, float]:
        return {rid: self.calibrate(p) for rid, p in probs.items()}
