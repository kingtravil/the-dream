"""Horse form features — leakage-safe via cutoff timestamp."""

from __future__ import annotations

from typing import Dict, List

from the_dream.ingest.form import FormRun
from the_dream.normalize.schema import RaceEvent, Runner


def _form_score(position: int, field_size: int = 12) -> float:
    if position <= 0:
        return 0.0
    return max(0.0, 1.0 - (position - 1) / max(field_size - 1, 1))


def horse_features(
    runner: Runner,
    race: RaceEvent,
    form_runs: List[FormRun],
    decision_cutoff_utc: int,
) -> Dict[str, float]:
    valid = [r for r in form_runs if r.race_date_utc <= decision_cutoff_utc]
    valid.sort(key=lambda r: r.race_date_utc, reverse=True)

    scores = [_form_score(r.finish_position) for r in valid]
    last_3 = scores[:3]
    last_10 = scores[:10]

    days_since = 999.0
    if valid:
        days_since = max(0.0, (decision_cutoff_utc - valid[0].race_date_utc) / 86400.0)

    last_dist = valid[0].distance_m if valid else race.distance_m
    distance_change = (race.distance_m - last_dist) / max(race.distance_m, 1)

    same_track = [r for r in valid if r.track == race.track]
    track_suit = sum(_form_score(r.finish_position) for r in same_track[:5]) / max(
        len(same_track[:5]), 1
    )

    same_going = [r for r in valid if r.condition == race.condition]
    going_suit = sum(_form_score(r.finish_position) for r in same_going[:5]) / max(
        len(same_going[:5]), 1
    )

    weights = [r.weight_kg for r in race.active_runners]
    avg_weight = sum(weights) / max(len(weights), 1)

    return {
        "avg_form_last_3": sum(last_3) / max(len(last_3), 1),
        "avg_form_last_10": sum(last_10) / max(len(last_10), 1),
        "days_since_run": days_since,
        "distance_change_effect": -abs(distance_change) * 0.1,
        "track_suitability": track_suit,
        "barrier_penalty": -max(0, runner.barrier - 8) * 0.02,
        "weight_vs_field": (runner.weight_kg - avg_weight) * -0.01,
        "class_move": 0.0,
        "going_suitability": going_suit,
    }
