"""Load Betfair historical price/stream + BSP from disk into canonical schema."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from the_dream.config import DreamConfig
from the_dream.ingest.betfair import snapshot_at_cutoff
from the_dream.normalize.dedupe import apply_scratchings
from the_dream.normalize.schema import BSPRecord, MarketSnapshot, RaceEvent, Runner


def decision_cutoff(start_time_utc: int, lead_seconds: int) -> int:
    return start_time_utc - lead_seconds


@dataclass
class HistoricalRace:
    """Raw historical race payload before cutoff reconstruction."""

    race: RaceEvent
    price_history: List[MarketSnapshot]
    bsp: List[BSPRecord]
    scratchings: List[dict] = field(default_factory=list)
    winner_id: Optional[str] = None


@dataclass
class HistoricalReplayRace:
    """Race ready for shadow replay: snapshots at decision_cutoff, BSP joined."""

    race: RaceEvent
    snapshots: List[MarketSnapshot]
    bsp: List[BSPRecord]
    winner_id: Optional[str] = None
    decision_cutoff_utc: int = 0


def _parse_runner(raw: dict) -> Runner:
    return Runner(
        runner_id=str(raw["runner_id"]),
        horse_id=str(raw.get("horse_id", raw["runner_id"])),
        jockey=str(raw.get("jockey", "unknown")),
        trainer=str(raw.get("trainer", "unknown")),
        barrier=int(raw.get("barrier", 0)),
        weight_kg=float(raw.get("weight_kg", 0.0)),
        is_scratched=bool(raw.get("is_scratched", False)),
    )


def _parse_snapshot(raw: dict) -> MarketSnapshot:
    ladder = raw.get("ladder", [])
    ladder_tuples = [(float(p), float(s)) for p, s in ladder]
    return MarketSnapshot(
        runner_id=str(raw["runner_id"]),
        back_price=float(raw["back_price"]),
        lay_price=float(raw.get("lay_price", raw["back_price"])),
        last_traded=float(raw.get("last_traded", raw["back_price"])),
        traded_volume=float(raw.get("traded_volume", 0.0)),
        ladder=ladder_tuples,
        timestamp_utc=int(raw["timestamp_utc"]),
    )


def parse_race_payload(payload: dict) -> HistoricalRace:
    runners = [_parse_runner(r) for r in payload["runners"]]
    race = RaceEvent(
        race_id=str(payload["race_id"]),
        track=str(payload.get("track", "unknown")),
        distance_m=int(payload.get("distance_m", 0)),
        condition=str(payload.get("condition", "unknown")),
        start_time_utc=int(payload["start_time_utc"]),
        runners=runners,
        region=str(payload.get("region", "NZ")),
    )
    history = [_parse_snapshot(s) for s in payload.get("price_history", [])]
    bsp = [BSPRecord(str(b["runner_id"]), float(b["bsp"])) for b in payload.get("bsp", [])]
    return HistoricalRace(
        race=race,
        price_history=history,
        bsp=bsp,
        scratchings=list(payload.get("scratchings", [])),
        winner_id=payload.get("winner_id"),
    )


def load_historical_file(path: Path) -> List[HistoricalRace]:
    """Load JSONL or JSON array of historical races."""
    text = path.read_text()
    races: List[HistoricalRace] = []
    if text.strip().startswith("["):
        for payload in json.loads(text):
            races.append(parse_race_payload(payload))
    else:
        for line in text.splitlines():
            line = line.strip()
            if line:
                races.append(parse_race_payload(json.loads(line)))
    return races


def load_historical_dir(directory: Path) -> List[HistoricalRace]:
    races: List[HistoricalRace] = []
    for path in sorted(directory.glob("*.jsonl")):
        races.extend(load_historical_file(path))
    for path in sorted(directory.glob("*.json")):
        races.extend(load_historical_file(path))
    return sorted(races, key=lambda r: r.race.start_time_utc)


def reconstruct_at_cutoff(
    historical: HistoricalRace,
    cfg: DreamConfig,
) -> HistoricalReplayRace:
    """
    Reconstruct ladder/prices AS AT decision_cutoff.
    Apply scratchings announced before cutoff. No forward-looking data.
    """
    cutoff = decision_cutoff(historical.race.start_time_utc, cfg.decision_lead_seconds)

    scratched_before_cutoff = [
        s["runner_id"]
        for s in historical.scratchings
        if int(s.get("timestamp_utc", 0)) <= cutoff
    ]
    race = apply_scratchings(historical.race, scratched_before_cutoff)

    valid_history = [s for s in historical.price_history if s.timestamp_utc <= cutoff]
    snapshots = snapshot_at_cutoff(valid_history, cutoff)

    active_ids = {r.runner_id for r in race.active_runners}
    snapshots = [s for s in snapshots if s.runner_id in active_ids]
    bsp = [b for b in historical.bsp if b.runner_id in active_ids]

    return HistoricalReplayRace(
        race=race,
        snapshots=snapshots,
        bsp=bsp,
        winner_id=historical.winner_id,
        decision_cutoff_utc=cutoff,
    )


def iter_replay_races(
    paths: List[Path],
    cfg: DreamConfig,
) -> Iterator[HistoricalReplayRace]:
    """Chronological replay iterator over one or more historical files/dirs."""
    all_races: List[HistoricalRace] = []
    for path in paths:
        if path.is_dir():
            all_races.extend(load_historical_dir(path))
        else:
            all_races.extend(load_historical_file(path))

    all_races.sort(key=lambda r: r.race.start_time_utc)
    for historical in all_races:
        yield reconstruct_at_cutoff(historical, cfg)
