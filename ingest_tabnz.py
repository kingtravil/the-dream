#!/usr/bin/env python3
"""Ingest TAB NZ affiliate race data — research/validation, no betting."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from the_dream.ingest.tabnz import TabNZClient, TabNZConfig, format_ingested, ingest_race

DEFAULT_FIXTURE = Path(__file__).parent / "data" / "tabnz" / "sample_race.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="TAB NZ affiliate ingestion (no betting)")
    parser.add_argument("event_id", nargs="?", default="f47ac10b-58cc-4372-a567-0e02b2c3d479")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--from-email", default="")
    parser.add_argument("--partner", default="")
    parser.add_argument("--partner-id", default="")
    args = parser.parse_args()

    cfg = TabNZConfig(
        from_email=args.from_email,
        x_partner=args.partner,
        x_partner_id=args.partner_id,
        fixture_path=args.fixture if not args.from_email else None,
    )
    client = TabNZClient(cfg)

    try:
        ingested = ingest_race(client, args.event_id)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(format_ingested(ingested))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
