"""
TAB NZ affiliate API client — ingestion only (no betting).

Base: https://api.tab.co.nz/affiliates/v1
Endpoints: meetings, race events (with fixed odds + flucs), results.

CLOSE benchmark: last fixed-odds price before race start — kept in a separate
bucket (BSPRecord), never mixed into the price timeline.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from the_dream.ingest.betfair_stream import IngestedMarket
from the_dream.ingest.tabnz_config import TabNZConfig
from the_dream.normalize.schema import BSPRecord, MarketSnapshot, RaceEvent, Runner

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "tabnz" / "sample_race.json"


@dataclass
class TabNZClient:
    """Read-only TAB NZ affiliate feed client."""

    config: TabNZConfig

    def _headers(self) -> Dict[str, str]:
        h = {
            "Accept": "application/json",
            "User-Agent": "THE-DREAM/0.1 (research; no betting)",
        }
        if self.config.from_email:
            h["From"] = self.config.from_email
        if self.config.x_partner:
            h["X-Partner"] = self.config.x_partner
        if self.config.x_partner_id:
            h["X-Partner-ID"] = self.config.x_partner_id
        return h

    def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> dict:
        if self.config.use_fixture:
            return self._load_fixture(path, params)

        base = self.config.base_url.rstrip("/")
        url = f"{base}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as exc:
            raise ConnectionError(f"TAB NZ API request failed: {exc}") from exc

    def _load_fixture(self, path: str, params: Optional[Dict[str, str]] = None) -> dict:
        fixture = self.config.fixture_path or DEFAULT_FIXTURE
        if not fixture.exists():
            raise FileNotFoundError(
                f"No TAB NZ credentials and no fixture at {fixture}. "
                "Set From/X-Partner headers or provide a sample JSON fixture."
            )
        store = json.loads(fixture.read_text())
        if "meetings" in path or path.endswith("meetings"):
            return store.get("meetings_response", store)
        if "meeting" in path:
            mid = (params or {}).get("id") or path.rstrip("/").split("/")[-1]
            meetings = store.get("meetings_response", {}).get("data", {}).get("meetings", [])
            for m in meetings:
                if m.get("meeting") == mid:
                    return {"header": {}, "params": {}, "data": {"meeting": m}}
            return store.get("meeting_response", store)
        # race / event
        race_id = (params or {}).get("id")
        if not race_id and "/events/" in path:
            race_id = path.split("/events/")[-1].split("?")[0]
        if race_id and store.get("race_response", {}).get("data", {}).get("race", {}).get("event_id") == race_id:
            return store["race_response"]
        return store.get("race_response", store)

    def list_meetings(
        self,
        *,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        country: str = "NZL",
        category: str = "T",
    ) -> dict:
        params: Dict[str, str] = {"enc": "json", "country": country, "type": category}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return self._get("racing/meetings", params)

    def get_meeting(self, meeting_id: str) -> dict:
        return self._get(f"racing/meetings/{meeting_id}", {"enc": "json"})

    def get_race(self, event_id: str) -> dict:
        """Race detail with runners, fixed odds, flucs, results when final."""
        return self._get(f"racing/events/{event_id}", {"enc": "json"})


def _parse_weight_kg(weight: Any) -> float:
    if weight is None:
        return 0.0
    if isinstance(weight, dict):
        raw = weight.get("total") or weight.get("allocated") or "0"
    else:
        raw = str(weight)
    raw = raw.lower().replace("kg", "").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _race_start_utc(race: dict) -> int:
    if race.get("advertised_start"):
        return int(race["advertised_start"])
    if race.get("start_time"):
        st = race["start_time"]
        if isinstance(st, (int, float)):
            return int(st)
        return _iso_to_epoch(str(st))
    return 0


def _iso_to_epoch(iso: str) -> int:
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _runner_id(runner: dict) -> str:
    return str(runner.get("competitor_id") or runner.get("runner_number") or runner.get("name"))


def _fixed_price(runner: dict) -> float:
    odds = runner.get("odds") or {}
    return float(odds.get("fixed_win") or 0.0)


def _build_snapshots_and_close(
    runners: List[dict],
    start_utc: int,
    fluc_interval_sec: int = 120,
) -> tuple[List[MarketSnapshot], List[BSPRecord]]:
    """
    Build price timeline from flucs; close = last fixed price before off.

    The close price is NEVER appended to snapshots.
    """
    snapshots: List[MarketSnapshot] = []
    close_records: List[BSPRecord] = []

    for runner in runners:
        if runner.get("is_scratched"):
            continue

        rid = _runner_id(runner)
        flucs: List[float] = [float(f) for f in (runner.get("flucs") or []) if float(f) > 1.0]
        close_price = _fixed_price(runner)

        if close_price <= 1.0 and flucs:
            close_price = flucs[-1]

        if close_price <= 1.0:
            continue

        # Timeline = flucs excluding the close (if present as final fluc)
        timeline = list(flucs)
        if timeline and abs(timeline[-1] - close_price) < 1e-9:
            timeline = timeline[:-1]

        # Also exclude any price at/after start from timeline
        for i, price in enumerate(timeline):
            ts = start_utc - (len(timeline) - i) * fluc_interval_sec
            if ts >= start_utc:
                continue
            snapshots.append(
                MarketSnapshot(
                    runner_id=rid,
                    back_price=price,
                    lay_price=price,
                    last_traded=price,
                    traded_volume=0.0,
                    ladder=[(price, 0.0)],
                    timestamp_utc=ts,
                )
            )

        close_records.append(BSPRecord(runner_id=rid, bsp=close_price))

    return snapshots, close_records


def parse_tabnz_race_payload(payload: dict) -> IngestedMarket:
    """Map TAB NZ race JSON into canonical RaceEvent + snapshots + close bucket."""
    data = payload.get("data", payload)
    race_raw = data.get("race", data)
    runners_raw: List[dict] = data.get("runners") or []

    start_utc = _race_start_utc(race_raw)
    race_id = str(race_raw.get("event_id") or race_raw.get("id") or "unknown")

    runners: List[Runner] = []
    for r in runners_raw:
        rid = _runner_id(r)
        runners.append(
            Runner(
                runner_id=rid,
                horse_id=str(r.get("competitor_id") or rid),
                jockey=str(r.get("jockey") or "unknown"),
                trainer=str(r.get("trainer_name") or r.get("trainer") or "unknown"),
                barrier=int(r.get("barrier") or r.get("runner_number") or 0),
                weight_kg=_parse_weight_kg(r.get("weight")),
                is_scratched=bool(r.get("is_scratched")),
            )
        )

    race = RaceEvent(
        race_id=race_id,
        track=str(race_raw.get("meeting_name") or race_raw.get("name") or "unknown"),
        distance_m=int(race_raw.get("distance") or 0),
        condition=str(race_raw.get("track_condition") or "unknown"),
        start_time_utc=start_utc,
        runners=runners,
        region="NZ",
    )

    snapshots, close_bucket = _build_snapshots_and_close(runners_raw, start_utc)

    if start_utc > 0:
        from the_dream.features import validate_snapshots_at_cutoff

        validate_snapshots_at_cutoff(snapshots, start_utc)

    # Sanity: close prices must not appear as final snapshot for same runner
    close_by_runner = {c.runner_id: c.bsp for c in close_bucket}
    for snap in snapshots:
        if snap.runner_id in close_by_runner:
            if snap.timestamp_utc >= start_utc:
                raise ValueError(f"Leakage: snapshot at/after race start for {snap.runner_id}")
            if (
                abs(snap.back_price - close_by_runner[snap.runner_id]) < 1e-9
                and snap.timestamp_utc >= start_utc - 1
            ):
                raise ValueError(
                    f"Close price leaked into timeline for runner {snap.runner_id}"
                )

    return IngestedMarket(race=race, snapshots=snapshots, bsp=close_bucket)


def ingest_race(client: TabNZClient, event_id: str) -> IngestedMarket:
    """Fetch one race and map to canonical schema."""
    payload = client.get_race(event_id)
    return parse_tabnz_race_payload(payload)


def format_ingested(ingested: IngestedMarket) -> str:
    """Human-readable debug output: runners, price timeline, close bucket."""
    lines: List[str] = []
    race = ingested.race
    lines.append("=" * 72)
    lines.append(f"RACE  {race.race_id}  ({race.track})")
    lines.append(f"  off (utc)  : {race.start_time_utc}")
    lines.append(f"  distance   : {race.distance_m}m  condition: {race.condition}")
    lines.append(f"  runners    : {len(race.runners)} ({len(race.active_runners)} active)")
    lines.append("-" * 72)
    lines.append("RUNNERS")
    for r in race.runners:
        tag = "SCRATCHED" if r.is_scratched else "active"
        lines.append(
            f"  {r.runner_id:>12}  #{r.barrier:>2}  {r.jockey[:20]:<20}  {tag}"
        )

    lines.append("-" * 72)
    lines.append(f"PRICE TIMELINE  ({len(ingested.snapshots)} snapshots — fixed odds only)")
    by_runner: Dict[str, List[MarketSnapshot]] = {}
    for s in ingested.snapshots:
        by_runner.setdefault(s.runner_id, []).append(s)

    for rid in sorted(by_runner, key=lambda x: (not x.isdigit(), x)):
        snaps = by_runner[rid]
        latest = max(snaps, key=lambda s: s.timestamp_utc)
        lines.append(
            f"  {rid:>12}  price={latest.back_price:>6.2f}  snaps={len(snaps)}  "
            f"last_ts={latest.timestamp_utc}"
        )

    lines.append("-" * 72)
    lines.append(f"CLOSE BUCKET  ({len(ingested.bsp)} records — separate from timeline)")
    if ingested.bsp:
        for c in sorted(ingested.bsp, key=lambda x: x.runner_id):
            lines.append(f"  {c.runner_id:>12}  close={c.bsp:.2f}")
    else:
        lines.append("  (none)")
    lines.append("-" * 72)
    lines.append("OK  close isolated from price timeline")
    return "\n".join(lines)
