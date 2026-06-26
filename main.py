#!/usr/bin/env python3
"""THE DREAM — entry point."""

from __future__ import annotations

import argparse
import json

from the_dream import __version__
from the_dream.backtest import BacktestEngine, ReplayRace, compute_metrics, metrics_report
from the_dream.config import DEFAULT_CONFIG, DreamConfig, OperatingMode
from the_dream.ingest.form import FormRun, FormStore
from the_dream.normalize.schema import BSPRecord, MarketSnapshot, RaceEvent, Runner
from the_dream.pipeline import DreamEngine


def _demo_race() -> ReplayRace:
    """Synthetic race for shadow CLV run (bet-nothing / paper demo)."""
    start = 1_700_000_000
    race = RaceEvent(
        race_id="demo-race-1",
        track="Ellerslie",
        distance_m=1600,
        condition="Good4",
        start_time_utc=start,
        runners=[
            Runner("R1", "H1", "Jockey A", "Trainer X", 3, 57.0),
            Runner("R2", "H2", "Jockey B", "Trainer Y", 7, 56.5),
            Runner("R3", "H3", "Jockey C", "Trainer Z", 1, 58.0),
        ],
        region="NZ",
    )
    cutoff = start - 120
    snapshots = [
        MarketSnapshot("R1", 3.2, 3.3, 3.2, 8000, [(3.2, 3000)], cutoff),
        MarketSnapshot("R2", 7.0, 7.2, 7.0, 4000, [(7.0, 1500)], cutoff),
        MarketSnapshot("R3", 4.5, 4.6, 4.5, 6000, [(4.5, 2000)], cutoff),
    ]
    bsp = [
        BSPRecord("R1", 3.0),
        BSPRecord("R2", 7.5),
        BSPRecord("R3", 4.2),
    ]
    return ReplayRace(race=race, snapshots=snapshots, bsp=bsp, winner_id="R1")


def _seed_form(store: FormStore) -> None:
    base = 1_699_000_000
    for i, horse in enumerate(["H1", "H2", "H3"]):
        for j in range(5):
            store.add_run(
                FormRun(
                    horse_id=horse,
                    race_date_utc=base - j * 86400 * 14,
                    finish_position=(i + j) % 5 + 1,
                    distance_m=1600,
                    track="Ellerslie",
                    condition="Good4",
                    weight_kg=57.0,
                    jockey=f"Jockey {chr(65 + i)}",
                    trainer=f"Trainer {chr(88 + i)}",
                    barrier=3,
                    sp=4.0 + j,
                )
            )


def run_shadow(cfg: DreamConfig) -> None:
    """Shadow run: evaluate race, log all decisions + CLV vs BSP."""
    store = FormStore()
    _seed_form(store)
    engine = DreamEngine(cfg=cfg, form_store=store)
    demo = _demo_race()
    outputs = engine.evaluate_race(demo.race, demo.snapshots)

    print(f"🐎 THE DREAM v{__version__} | Mode: {cfg.mode.value} | Region: {cfg.region}")
    print(f"Commission: {cfg.commission:.0%} | EV threshold: {cfg.ev_threshold}")
    print("---")
    for out in outputs:
        print(json.dumps(out, indent=2))

    for bsp in demo.bsp:
        engine.ledger.update_with_bsp(bsp.runner_id, demo.race.race_id, bsp.bsp)

    bt = BacktestEngine(cfg=cfg, form_store=store)
    bt.ledger = engine.ledger
    metrics = compute_metrics(bt.ledger)
    print("---")
    print(metrics_report(metrics))


def run_backtest(cfg: DreamConfig) -> None:
    store = FormStore()
    _seed_form(store)
    engine = BacktestEngine(cfg=cfg, form_store=store)
    demo = _demo_race()
    engine.replay_all([demo])
    print(metrics_report(compute_metrics(engine.ledger)))


def main() -> None:
    parser = argparse.ArgumentParser(description="THE DREAM racing engine")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in OperatingMode],
        default=DEFAULT_CONFIG.mode.value,
    )
    parser.add_argument("--region", default=DEFAULT_CONFIG.region)
    parser.add_argument("--command", choices=["shadow", "backtest", "evaluate"], default="shadow")
    args = parser.parse_args()

    cfg = DreamConfig(
        mode=OperatingMode(args.mode),
        region=args.region,
    )

    if args.command == "shadow":
        run_shadow(cfg)
    elif args.command == "backtest":
        run_backtest(cfg)
    else:
        run_shadow(cfg)


if __name__ == "__main__":
    main()
