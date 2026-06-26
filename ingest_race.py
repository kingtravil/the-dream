#!/usr/bin/env python3
"""
THE DREAM — Betfair historical ingestion (build-first).

Reads real Betfair stream JSON (+ optional BSP CSV) and prints structured
RaceEvent + MarketSnapshots. BSP stays in its own bucket — never in the price stream.

Usage:
  python ingest_race.py data/betfair/sample_stream.jsonl
  python ingest_race.py race.json.bz2 --bsp bsp.csv
  python ingest_race.py data/historical/sample_races.jsonl --format simplified
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from the_dream.ingest.betfair_stream import (
    IngestedMarket,
    apply_bsp_csv,
    parse_betfair_stream,
)
from the_dream.ingest.historical import load_historical_file
from the_dream.normalize.schema import BSPRecord, MarketSnapshot, RaceEvent


def _load_simplified(path: Path) -> IngestedMarket:
    """Our pre-normalised JSONL — already keeps BSP separate from price_history."""
    races = load_historical_file(path)
    if not races:
        raise ValueError(f"No races in {path}")
    r = races[0]
    return IngestedMarket(race=r.race, snapshots=r.price_history, bsp=r.bsp)


def _print_ingested(ingested: IngestedMarket, verbose: bool = False) -> None:
    race = ingested.race
    print("=" * 72)
    print(f"RACE  {race.race_id}")
    print(f"  track      : {race.track}")
    print(f"  distance   : {race.distance_m}m")
    print(f"  off (utc)  : {race.start_time_utc}")
    print(f"  region     : {race.region}")
    print(f"  runners    : {len(race.runners)} ({len(race.active_runners)} active)")
    print("-" * 72)
    print("RUNNERS")
    for r in race.runners:
        tag = "SCRATCHED" if r.is_scratched else "active"
        print(f"  {r.runner_id:>12}  barrier={r.barrier:>2}  {tag}")

    print("-" * 72)
    print(f"PRICE TIMELINE  ({len(ingested.snapshots)} snapshots — exchange only)")

    by_runner: dict[str, list[MarketSnapshot]] = {}
    for s in ingested.snapshots:
        by_runner.setdefault(s.runner_id, []).append(s)

    for rid in sorted(by_runner, key=lambda x: int(x) if x.isdigit() else x):
        snaps = by_runner[rid]
        latest = max(snaps, key=lambda s: s.timestamp_utc)
        print(
            f"  {rid:>12}  back={latest.back_price:>6.2f}  "
            f"lay={latest.lay_price:>6.2f}  ltp={latest.last_traded:>6.2f}  "
            f"snaps={len(snaps)}"
        )
        if verbose:
            for s in sorted(snaps, key=lambda x: x.timestamp_utc)[-3:]:
                print(
                    f"             ts={s.timestamp_utc}  "
                    f"back={s.back_price:.2f}  vol={s.traded_volume:.0f}"
                )

    print("-" * 72)
    print(f"BSP BUCKET  ({len(ingested.bsp)} records — separate from price timeline)")
    if ingested.bsp:
        for b in sorted(ingested.bsp, key=lambda x: x.runner_id):
            print(f"  {b.runner_id:>12}  bsp={b.bsp:.2f}")
    else:
        print("  (none — provide --bsp CSV or use stream with bspReconciled)")

    # Sanity: BSP must not appear in snapshot list
    snap_bsp_leak = [s for s in ingested.snapshots if "bsp" in str(s).lower()]
    assert not snap_bsp_leak, "BSP leaked into snapshots"
    print("-" * 72)
    print("OK  BSP isolated from price timeline")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Betfair historical data")
    parser.add_argument("path", type=Path, help="Stream .json/.jsonl/.bz2 or simplified JSONL")
    parser.add_argument("--bsp", type=Path, default=None, help="Optional BSP CSV overlay")
    parser.add_argument(
        "--format",
        choices=["stream", "simplified", "auto"],
        default="auto",
        help="Input format (auto: .jsonl simplified if pre-normalised keys present)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show per-snapshot detail")
    parser.add_argument("--json", action="store_true", help="Dump structured JSON to stdout")
    args = parser.parse_args()

    if not args.path.exists():
        print(f"ERROR: file not found: {args.path}", file=sys.stderr)
        return 1

    fmt = args.format
    if fmt == "auto":
        peek = args.path.read_text()[:800]
        if '"price_history"' in peek or ('"race_id"' in peek and '"op"' not in peek):
            fmt = "simplified"
        else:
            fmt = "stream"

    try:
        if fmt == "simplified":
            ingested = _load_simplified(args.path)
        else:
            ingested = parse_betfair_stream(args.path)

        if args.bsp:
            ingested = apply_bsp_csv(ingested, args.bsp)

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "race": {
                "race_id": ingested.race.race_id,
                "track": ingested.race.track,
                "distance_m": ingested.race.distance_m,
                "start_time_utc": ingested.race.start_time_utc,
                "region": ingested.race.region,
                "runners": [
                    {
                        "runner_id": r.runner_id,
                        "barrier": r.barrier,
                        "is_scratched": r.is_scratched,
                    }
                    for r in ingested.race.runners
                ],
            },
            "snapshots": [
                {
                    "runner_id": s.runner_id,
                    "back_price": s.back_price,
                    "lay_price": s.lay_price,
                    "last_traded": s.last_traded,
                    "timestamp_utc": s.timestamp_utc,
                }
                for s in ingested.snapshots
            ],
            "bsp": [{"runner_id": b.runner_id, "bsp": b.bsp} for b in ingested.bsp],
        }
        print(json.dumps(payload, indent=2))
    else:
        _print_ingested(ingested, verbose=args.verbose)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
