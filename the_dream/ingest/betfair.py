"""Betfair exchange stream + REST (primary data source)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

from the_dream.normalize.schema import BSPRecord, MarketSnapshot, RaceEvent


@dataclass
class BetfairCredentials:
    app_key: str
    session_token: str
    use_delayed: bool = True


class BetfairClient(Protocol):
    def list_market_book(self, market_id: str) -> List[MarketSnapshot]: ...

    def get_bsp(self, market_id: str) -> List[BSPRecord]: ...

    def stream_prices(self, market_id: str) -> None: ...


class BetfairRESTClient:
    """REST client skeleton — wire to real API when credentials are available."""

    def __init__(self, credentials: Optional[BetfairCredentials] = None) -> None:
        self.credentials = credentials

    def list_market_book(self, market_id: str) -> List[MarketSnapshot]:
        raise NotImplementedError(
            "Connect Betfair API credentials to fetch live market books."
        )

    def get_bsp(self, market_id: str) -> List[BSPRecord]:
        raise NotImplementedError(
            "Connect Betfair API credentials to fetch BSP records."
        )

    def stream_prices(self, market_id: str) -> None:
        raise NotImplementedError(
            "Connect Betfair Stream API for live price streaming."
        )


def snapshot_at_cutoff(
    snapshots: List[MarketSnapshot],
    decision_cutoff_utc: int,
) -> List[MarketSnapshot]:
    """Select the latest snapshot per runner at or before decision cutoff."""
    by_runner: Dict[str, MarketSnapshot] = {}
    for snap in snapshots:
        if snap.timestamp_utc > decision_cutoff_utc:
            continue
        existing = by_runner.get(snap.runner_id)
        if existing is None or snap.timestamp_utc > existing.timestamp_utc:
            by_runner[snap.runner_id] = snap
    return list(by_runner.values())


def race_from_betfair_payload(payload: dict) -> RaceEvent:
    """Parse a Betfair market catalogue payload into a RaceEvent."""
    runners = [
        Runner(
            runner_id=str(r["selectionId"]),
            horse_id=str(r.get("metadata", {}).get("SIRE_NAME", r["selectionId"])),
            jockey=r.get("metadata", {}).get("JOCKEY_NAME", "unknown"),
            trainer=r.get("metadata", {}).get("TRAINER_NAME", "unknown"),
            barrier=int(r.get("metadata", {}).get("STALL_DRAW", 0) or 0),
            weight_kg=float(r.get("metadata", {}).get("WEIGHT_VALUE", 0) or 0),
            is_scratched=bool(r.get("status") == "REMOVED"),
        )
        for r in payload.get("runners", [])
    ]
    desc = payload.get("description", {})
    return RaceEvent(
        race_id=str(payload.get("marketId", "")),
        track=desc.get("venue", "unknown"),
        distance_m=int(desc.get("distance", 0) or 0),
        condition=desc.get("going", "unknown"),
        start_time_utc=int(payload.get("marketStartTime", 0)),
        runners=runners,
        region=payload.get("region", "NZ"),
    )
