"""Historical form / jockey / trainer / track data ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class FormRun:
    horse_id: str
    race_date_utc: int
    finish_position: int
    distance_m: int
    track: str
    condition: str
    weight_kg: float
    jockey: str
    trainer: str
    barrier: int
    sp: float


class FormStore:
    """In-memory form history store; replace with DB in production."""

    def __init__(self) -> None:
        self._runs: Dict[str, List[FormRun]] = {}

    def add_run(self, run: FormRun) -> None:
        self._runs.setdefault(run.horse_id, []).append(run)

    def runs_before(
        self,
        horse_id: str,
        cutoff_utc: int,
    ) -> List[FormRun]:
        runs = self._runs.get(horse_id, [])
        return [r for r in runs if r.race_date_utc <= cutoff_utc]
