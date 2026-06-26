"""Jockey and trainer statistics — cutoff-safe."""

from __future__ import annotations

from typing import Dict, List

from the_dream.ingest.form import FormRun
from the_dream.normalize.schema import Runner


def jockey_trainer_features(
    runner: Runner,
    form_runs: List[FormRun],
    decision_cutoff_utc: int,
    race_track: str = "",
) -> Dict[str, float]:
    valid = [r for r in form_runs if r.race_date_utc <= decision_cutoff_utc]

    jockey_runs = [r for r in valid if r.jockey == runner.jockey]
    trainer_runs = [r for r in valid if r.trainer == runner.trainer]
    jt_runs = [
        r for r in valid if r.jockey == runner.jockey and r.trainer == runner.trainer
    ]

    def win_rate(runs: List[FormRun]) -> float:
        if not runs:
            return 0.0
        wins = sum(1 for r in runs if r.finish_position == 1)
        return wins / len(runs)

    def roi_vs_market(runs: List[FormRun]) -> float:
        if not runs:
            return 0.0
        total = 0.0
        for r in runs:
            implied = 1.0 / r.sp if r.sp > 1.0 else 0.0
            actual = 1.0 if r.finish_position == 1 else 0.0
            total += actual - implied
        return total / len(runs)

    first_up = [r for r in trainer_runs if r.finish_position > 0][:1]

    return {
        "jockey_win_rate": win_rate(jockey_runs),
        "jockey_roi_vs_market": roi_vs_market(jockey_runs),
        "trainer_win_rate": win_rate(trainer_runs),
        "jt_synergy": win_rate(jt_runs),
        "trainer_first_up_pattern": 1.0 if first_up and first_up[0].finish_position <= 3 else 0.0,
        "track_specialisation": win_rate(
            [r for r in trainer_runs if r.track == race_track]
        ) if race_track else 0.0,
    }
