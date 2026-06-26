"""Build full feature vectors for all runners in a race."""

from __future__ import annotations

from typing import Dict, List, Optional

from the_dream.features.horse import horse_features
from the_dream.features.jockey import jockey_trainer_features
from the_dream.features.market import market_features
from the_dream.features.registry import FEATURE_REGISTRY_V1, feature_hash
from the_dream.ingest.form import FormRun, FormStore
from the_dream.normalize.schema import MarketSnapshot, RaceEvent
from the_dream.model.ensemble import ProbabilityEnsemble


def decision_cutoff(start_time_utc: int, lead_seconds: int) -> int:
    return start_time_utc - lead_seconds


def validate_snapshots_at_cutoff(
    snapshots: List[MarketSnapshot],
    decision_cutoff_utc: int,
) -> None:
    """Reject any price snapshot taken after the decision cutoff."""
    for snap in snapshots:
        if snap.timestamp_utc > decision_cutoff_utc:
            raise ValueError(
                f"Leakage detected: snapshot for {snap.runner_id} at "
                f"ts={snap.timestamp_utc} > cutoff={decision_cutoff_utc}"
            )


def build_race_features(
    race: RaceEvent,
    snapshots: List[MarketSnapshot],
    form_store: FormStore,
    lead_seconds: int,
    prior_snapshots: Optional[List[MarketSnapshot]] = None,
) -> Dict[str, Dict[str, float]]:
    cutoff = decision_cutoff(race.start_time_utc, lead_seconds)
    validate_snapshots_at_cutoff(snapshots, cutoff)
    if prior_snapshots:
        validate_snapshots_at_cutoff(prior_snapshots, cutoff)

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
            vec.update(market_features(snap, prior, decision_cutoff_utc=cutoff))
        features[runner.runner_id] = vec
    return features


def assert_no_leakage(
    feature_timestamps: Dict[str, int],
    decision_cutoff_utc: int,
) -> None:
    for name, ts in feature_timestamps.items():
        if ts > decision_cutoff_utc:
            raise ValueError(f"Leakage detected in feature {name}: ts={ts} > cutoff")


def renormalize_after_scratch(
    p_model: Dict[str, float],
    p_market: Dict[str, float],
    scratched_ids: List[str],
) -> tuple[Dict[str, float], Dict[str, float]]:
    """Re-normalize model and market probs after a post-snapshot scratching."""
    ensemble = ProbabilityEnsemble()
    new_model = ensemble.renormalize_on_scratch(p_model, scratched_ids)
    scratched_set = set(scratched_ids)
    active_market = {rid: p for rid, p in p_market.items() if rid not in scratched_set}
    total = sum(active_market.values())
    if total <= 0:
        return new_model, active_market
    new_market = {rid: p / total for rid, p in active_market.items()}
    return new_model, new_market
