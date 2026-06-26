"""
Parse real Betfair historical stream JSON into RaceEvent + MarketSnapshots.

BSP (the close) is kept in a SEPARATE list — never mixed into the price timeline.
Stream rc fields spb/spl/spn/spf are ignored for snapshots; final BSP comes from
marketDefinition runners when bspReconciled=true, or an optional BSP CSV.
"""

from __future__ import annotations

import bz2
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, TextIO, Tuple

from the_dream.normalize.schema import BSPRecord, MarketSnapshot, RaceEvent, Runner

# Runner-change keys that are EXCHANGE prices — safe for snapshots.
_EXCHANGE_RC_KEYS = frozenset({"batb", "batl", "atb", "atl", "trd", "ltp", "tv"})

# BSP / projected-SP keys — NEVER go into the price timeline.
_BSP_RC_KEYS = frozenset({"spb", "spl", "spn", "spf", "bdatb", "bdatl"})


@dataclass
class IngestedMarket:
    """Structured output: race metadata, price timeline, BSP in its own bucket."""

    race: RaceEvent
    snapshots: List[MarketSnapshot]
    bsp: List[BSPRecord]


@dataclass
class _RunnerBook:
    selection_id: str
    name: str = ""
    sort_priority: int = 0
    status: str = "ACTIVE"
    batb: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    batl: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    atb: Dict[float, float] = field(default_factory=dict)
    atl: Dict[float, float] = field(default_factory=dict)
    ltp: float = 0.0
    tv: float = 0.0

    def best_back(self) -> float:
        if self.batb:
            lvl0 = self.batb.get(0)
            if lvl0 and lvl0[0] > 1.0:
                return lvl0[0]
            prices = [p for p, s in self.batb.values() if s > 0 and p > 1.0]
            return max(prices) if prices else 0.0
        if self.atb:
            prices = [p for p, s in self.atb.items() if s > 0 and p > 1.0]
            return max(prices) if prices else 0.0
        return self.ltp if self.ltp > 1.0 else 0.0

    def best_lay(self) -> float:
        if self.batl:
            lvl0 = self.batl.get(0)
            if lvl0 and lvl0[0] > 1.0:
                return lvl0[0]
            prices = [p for p, s in self.batl.values() if s > 0 and p > 1.0]
            return min(prices) if prices else 0.0
        if self.atl:
            prices = [p for p, s in self.atl.items() if s > 0 and p > 1.0]
            return min(prices) if prices else 0.0
        return 0.0

    def ladder(self) -> List[Tuple[float, float]]:
        if self.atb:
            return sorted(
                [(p, s) for p, s in self.atb.items() if s > 0],
                key=lambda x: -x[0],
            )[:5]
        levels = sorted(self.batb.items())
        return [(p, s) for _, (p, s) in levels if s > 0][:5]

    def to_snapshot(self, timestamp_utc: int) -> Optional[MarketSnapshot]:
        back = self.best_back()
        if back <= 1.0:
            return None
        lay = self.best_lay()
        if lay <= 1.0:
            lay = back * 1.02
        return MarketSnapshot(
            runner_id=self.selection_id,
            back_price=back,
            lay_price=lay,
            last_traded=self.ltp if self.ltp > 1.0 else back,
            traded_volume=self.tv,
            ladder=self.ladder(),
            timestamp_utc=timestamp_utc,
        )


def _parse_iso_to_epoch(iso: str) -> int:
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _open_stream(path: Path) -> TextIO:
    if path.suffix == ".bz2":
        raw = bz2.open(path, "rt", encoding="utf-8")
        return raw  # type: ignore[return-value]
    return path.open(encoding="utf-8")


def _iter_stream_lines(path: Path) -> Iterator[dict]:
    with _open_stream(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _apply_level_ladder(
    book: Dict[int, Tuple[float, float]],
    updates: List[List[float]],
) -> None:
    for row in updates:
        if len(row) < 3:
            continue
        level = int(row[0])
        price = float(row[1])
        size = float(row[2])
        if size <= 0:
            book.pop(level, None)
        else:
            book[level] = (price, size)


def _apply_price_ladder(book: Dict[float, float], updates: List[List[float]]) -> None:
    for row in updates:
        if len(row) < 2:
            continue
        price = float(row[0])
        size = float(row[1])
        if size <= 0:
            book.pop(price, None)
        else:
            book[price] = size


def _apply_runner_change(book: _RunnerBook, rc: dict) -> bool:
    """Apply exchange-only rc deltas. Returns True if book changed."""
    changed = False
    for key, val in rc.items():
        if key in _BSP_RC_KEYS:
            continue
        if key not in _EXCHANGE_RC_KEYS:
            continue
        if key == "batb":
            _apply_level_ladder(book.batb, val)
            changed = True
        elif key == "batl":
            _apply_level_ladder(book.batl, val)
            changed = True
        elif key == "atb":
            _apply_price_ladder(book.atb, val)
            changed = True
        elif key == "atl":
            _apply_price_ladder(book.atl, val)
            changed = True
        elif key == "trd":
            _apply_price_ladder(book.atb, val)  # track traded; ltp/tv carry truth
            changed = True
        elif key == "ltp":
            book.ltp = float(val)
            changed = True
        elif key == "tv":
            book.tv = float(val)
            changed = True
    return changed


def _runners_from_definition(runners_raw: List[dict]) -> Dict[str, _RunnerBook]:
    books: Dict[str, _RunnerBook] = {}
    for i, r in enumerate(runners_raw):
        sid = str(r["id"])
        books[sid] = _RunnerBook(
            selection_id=sid,
            name=str(r.get("name", sid)),
            sort_priority=int(r.get("sortPriority", i + 1)),
            status=str(r.get("status", "ACTIVE")),
        )
    return books


def _race_from_definition(market_id: str, md: dict) -> RaceEvent:
    market_time = md.get("marketTime") or md.get("openDate") or ""
    start_utc = _parse_iso_to_epoch(market_time) if market_time else 0

    runners: List[Runner] = []
    for r in md.get("runners", []):
        status = str(r.get("status", "ACTIVE"))
        name = str(r.get("name", ""))
        parts = name.split(".", 1)
        barrier = 0
        if parts and parts[0].strip().isdigit():
            barrier = int(parts[0].strip())
        runners.append(
            Runner(
                runner_id=str(r["id"]),
                horse_id=str(r["id"]),
                jockey="unknown",
                trainer="unknown",
                barrier=barrier,
                weight_kg=0.0,
                is_scratched=status == "REMOVED",
            )
        )

    region = _region_from_md(md)
    distance_m = _distance_from_name(str(md.get("name", "")))

    return RaceEvent(
        race_id=market_id,
        track=str(md.get("venue", "unknown")),
        distance_m=distance_m,
        condition="unknown",
        start_time_utc=start_utc,
        runners=runners,
        region=region,
    )


def _region_from_md(md: dict) -> str:
    cc = str(md.get("countryCode", "")).upper()
    if cc == "NZ":
        return "NZ"
    if cc == "AU":
        return "AU_NSW"
    return "NZ"


def _distance_from_name(name: str) -> int:
    for token in name.replace("m", " m ").split():
        if token.isdigit():
            return int(token)
    return 0


def _collect_bsp_from_definition(md: dict) -> List[BSPRecord]:
    """Final BSP lives on marketDefinition runners after reconciliation."""
    if not md.get("bspReconciled"):
        return []
    out: List[BSPRecord] = []
    for r in md.get("runners", []):
        bsp_val = r.get("bsp")
        if bsp_val is not None and float(bsp_val) > 1.0:
            out.append(BSPRecord(runner_id=str(r["id"]), bsp=float(bsp_val)))
    return out


def parse_betfair_stream(path: Path) -> IngestedMarket:
    """
    Parse one Betfair historical stream file (JSON lines, optionally .bz2).

    Price timeline = exchange snapshots only.
    BSP = separate list from reconciled marketDefinition or CSV overlay.
    """
    market_id = ""
    race: Optional[RaceEvent] = None
    books: Dict[str, _RunnerBook] = {}
    snapshots: List[MarketSnapshot] = []
    bsp: List[BSPRecord] = []
    last_md: Optional[dict] = None

    for msg in _iter_stream_lines(path):
        if msg.get("op") != "mcm":
            continue
        pt_ms = int(msg.get("pt", 0))
        ts = pt_ms // 1000 if pt_ms > 1_000_000_000_000 else pt_ms

        for mc in msg.get("mc", []):
            market_id = str(mc.get("id", market_id))

            if "marketDefinition" in mc:
                md = mc["marketDefinition"]
                last_md = md
                race = _race_from_definition(market_id, md)
                books = _runners_from_definition(md.get("runners", []))
                reconciled = _collect_bsp_from_definition(md)
                if reconciled:
                    bsp = reconciled

            if "rc" not in mc:
                continue

            any_change = False
            for rc in mc["rc"]:
                sid = str(rc.get("id", ""))
                if sid not in books:
                    books[sid] = _RunnerBook(selection_id=sid)
                if _apply_runner_change(books[sid], rc):
                    any_change = True

            if any_change:
                for book in books.values():
                    if book.status == "REMOVED":
                        continue
                    snap = book.to_snapshot(ts)
                    if snap:
                        snapshots.append(snap)

    if race is None:
        raise ValueError(f"No marketDefinition found in {path}")

    return IngestedMarket(race=race, snapshots=snapshots, bsp=bsp)


def load_bsp_csv(path: Path) -> Dict[Tuple[str, str], float]:
    """
    Load optional BSP CSV keyed by (market_id, selection_id).

    Accepts flexible column names: market_id, selection_id, bsp.
    """
    mapping: Dict[Tuple[str, str], float] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return mapping
        fields = {h.lower().strip(): h for h in reader.fieldnames}
        mid_col = fields.get("market_id") or fields.get("marketid")
        sid_col = fields.get("selection_id") or fields.get("selectionid")
        bsp_col = fields.get("bsp") or fields.get("bsp_price")
        if not all([mid_col, sid_col, bsp_col]):
            raise ValueError(
                f"BSP CSV needs market_id, selection_id, bsp columns; got {reader.fieldnames}"
            )
        for row in reader:
            mid = str(row[mid_col]).strip()
            sid = str(row[sid_col]).strip()
            bsp = float(row[bsp_col])
            if bsp > 1.0:
                mapping[(mid, sid)] = bsp
    return mapping


def apply_bsp_csv(ingested: IngestedMarket, csv_path: Path) -> IngestedMarket:
    """Overlay BSP from CSV into the separate BSP bucket (never touches snapshots)."""
    mapping = load_bsp_csv(csv_path)
    race_id = ingested.race.race_id
    bsp_records = [
        BSPRecord(runner_id=sid, bsp=price)
        for (mid, sid), price in mapping.items()
        if mid == race_id
    ]
    if not bsp_records:
        bsp_records = [
            BSPRecord(runner_id=sid, bsp=price)
            for (_, sid), price in mapping.items()
        ]
    return IngestedMarket(
        race=ingested.race,
        snapshots=ingested.snapshots,
        bsp=bsp_records or ingested.bsp,
    )
