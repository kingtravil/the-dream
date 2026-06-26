"""Build full feature vectors for all runners in a race."""

from __future__ import annotations

from typing import Dict, List, Optional

from the_dream.features.horse import horse_features
from the_dream.features.jockey import jockey_trainer_features
from the_dream.features.market import market_features
from the_dream.features.registry import FEATURE_REGISTRY_V1, feature_hash
from the_dream.ingest.form import FormRun, FormStore
from the_dream.normalize.schema import MarketSnapshot, RaceEvent


def decision_cutoff(start_time_utc: int, lead_seconds: int) -> int:
    return start_time_utc - lead_seconds


def build_race_features(
    race: RaceEvent,
    snapshots: List[MarketSnapshot],
    form_store: FormStore,
    lead_seconds: int,
    prior_snapshots: Optional[List[MarketSnapshot]] = None,
) -> Dict[str, Dict[str, float]]:
    cutoff = decision_cutoff(race.start_time_utc, lead_seconds)
    snap_by_runner = {s.runner_id: s for s in snapshots}
    prior_by_runner = {s.runner_id: s for s in (prior_snapshots or [])}

    features: Dict[str, Dict[str, float]] = {}
    for runner in race.active_runners:
        form_runs = form_store.runs_before(runner.horse_id, cutoff)
        vec = {}
        vec.update(horse_features(runner, race, form_runs, cutoff))
        vec.update(jockey_trainer_features(runner, form_runs, cutoff, race.track))
        snap = snap_by_runner.get(runner.runner_id)
        if snap:
            prior = prior_by_runner.get(runner.runner_id)
            vec.update(market_features(snap, prior))
        features[runner.runner_id] = vec
    return features


def assert_no_leakage(
    feature_timestamps: Dict[str, int],
    decision_cutoff_utc: int,
) -> None:
    for name, ts in feature_timestamps.items():
        if ts > decision_cutoff_utc:
            raise ValueError(f"Leakage detected in feature {name}: ts={ts} > cutoff")
