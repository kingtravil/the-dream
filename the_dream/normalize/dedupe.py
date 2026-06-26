"""Runner-id reconciliation across sources and scratching handling."""

from __future__ import annotations

from typing import Dict, Iterable, List, Set

from the_dream.normalize.schema import RaceEvent, Runner


def reconcile_runner_ids(
    primary: List[Runner],
    aliases: Dict[str, str],
) -> List[Runner]:
    """Map external runner ids to canonical ids via alias table."""
    reconciled: List[Runner] = []
    for runner in primary:
        canonical_id = aliases.get(runner.runner_id, runner.runner_id)
        reconciled.append(
            Runner(
                runner_id=canonical_id,
                horse_id=runner.horse_id,
                jockey=runner.jockey,
                trainer=runner.trainer,
                barrier=runner.barrier,
                weight_kg=runner.weight_kg,
                is_scratched=runner.is_scratched,
            )
        )
    return reconciled


def apply_scratchings(race: RaceEvent, scratched_ids: Iterable[str]) -> RaceEvent:
    """Return a new RaceEvent with scratchings applied."""
    scratched: Set[str] = set(scratched_ids)
    updated = [
        Runner(
            runner_id=r.runner_id,
            horse_id=r.horse_id,
            jockey=r.jockey,
            trainer=r.trainer,
            barrier=r.barrier,
            weight_kg=r.weight_kg,
            is_scratched=r.is_scratched or r.runner_id in scratched,
        )
        for r in race.runners
    ]
    return RaceEvent(
        race_id=race.race_id,
        track=race.track,
        distance_m=race.distance_m,
        condition=race.condition,
        start_time_utc=race.start_time_utc,
        runners=updated,
        region=race.region,
    )
