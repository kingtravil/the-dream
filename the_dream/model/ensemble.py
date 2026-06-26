"""Ensemble blends + enforces sum-to-1 per race."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from the_dream.model.calibrate import Calibrator
from the_dream.model.lgbm import LGBMModel
from the_dream.model.logit import ConditionalLogit, softmax


@dataclass
class EnsembleOutput:
    probabilities: Dict[str, float]
    lgbm_probs: Dict[str, float]
    logit_probs: Dict[str, float]
    confidence: Dict[str, float]


class ProbabilityEnsemble:
    def __init__(
        self,
        lgbm_weight: float = 0.6,
        logit_weight: float = 0.4,
    ) -> None:
        self.lgbm = LGBMModel()
        self.logit = ConditionalLogit()
        self.calibrator = Calibrator()
        self.lgbm_weight = lgbm_weight
        self.logit_weight = logit_weight

    def predict_race(
        self,
        features_by_runner: Dict[str, Dict[str, float]],
        scratched: Optional[List[str]] = None,
    ) -> EnsembleOutput:
        scratched_set = set(scratched or [])
        active = {
            rid: feats for rid, feats in features_by_runner.items() if rid not in scratched_set
        }

        lgbm_raw = {rid: self.lgbm.predict_proba(f) for rid, f in active.items()}
        utilities = self.logit.utilities_from_features(active)
        logit_raw = self.logit.predict_race(utilities)

        blended: Dict[str, float] = {}
        for rid in active:
            blended[rid] = (
                self.lgbm_weight * lgbm_raw[rid] + self.logit_weight * logit_raw[rid]
            )

        calibrated = self.calibrator.calibrate_batch(blended)
        normalized = softmax(calibrated)

        confidence: Dict[str, float] = {}
        for rid in active:
            agreement = 1.0 - abs(lgbm_raw[rid] - logit_raw[rid])
            liquidity = active[rid].get("liquidity_pressure", 0.5)
            confidence[rid] = min(max(0.5 * agreement + 0.5 * liquidity, 0.0), 1.0)

        return EnsembleOutput(
            probabilities=normalized,
            lgbm_probs=lgbm_raw,
            logit_probs=logit_raw,
            confidence=confidence,
        )

    def renormalize_on_scratch(
        self,
        probs: Dict[str, float],
        scratched: List[str],
    ) -> Dict[str, float]:
        active = {rid: p for rid, p in probs.items() if rid not in scratched}
        return softmax(active)
