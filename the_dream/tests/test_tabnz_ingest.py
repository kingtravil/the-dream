"""TAB NZ affiliate ingestion smoke tests."""

from pathlib import Path

import pytest

from the_dream.features import validate_snapshots_at_cutoff
from the_dream.ingest.tabnz import (
    DEFAULT_FIXTURE,
    TabNZClient,
    TabNZConfig,
    format_ingested,
    ingest_race,
    parse_tabnz_race_payload,
)

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "tabnz" / "sample_race.json"


def test_tabnz_fixture_ingest_end_to_end(capsys):
    client = TabNZClient(TabNZConfig(fixture_path=FIXTURE))
    ingested = ingest_race(client, "f47ac10b-58cc-4372-a567-0e02b2c3d479")

    assert ingested.race.race_id == "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    assert ingested.race.track == "Ellerslie"
    assert len(ingested.race.active_runners) == 3
    assert len(ingested.snapshots) > 0
    assert len(ingested.bsp) == 3

    start = ingested.race.start_time_utc
    validate_snapshots_at_cutoff(ingested.snapshots, start)

    close_by_runner = {c.runner_id: c.bsp for c in ingested.bsp}
    for snap in ingested.snapshots:
        assert snap.timestamp_utc < start
        close = close_by_runner.get(snap.runner_id)
        if close and abs(snap.back_price - close) < 1e-9:
            pytest.fail(f"close price {close} found in timeline for {snap.runner_id}")

    output = format_ingested(ingested)
    print(output)
    captured = capsys.readouterr()
    assert "PRICE TIMELINE" in output
    assert "CLOSE BUCKET" in output
    assert "close isolated" in output


def test_tabnz_close_equals_last_fixed_odds_not_in_timeline():
    payload = __import__("json").loads(FIXTURE.read_text())["race_response"]
    ingested = parse_tabnz_race_payload(payload)

    assert ingested.bsp[0].runner_id == "nz-1001"
    assert ingested.bsp[0].bsp == 3.50

    runner1_snaps = [s for s in ingested.snapshots if s.runner_id == "nz-1001"]
    assert all(s.back_price != 3.50 for s in runner1_snaps)
    assert max(s.back_price for s in runner1_snaps) == pytest.approx(4.2)
    assert min(s.back_price for s in runner1_snaps) == pytest.approx(3.6)


def test_tabnz_offline_without_credentials():
    client = TabNZClient(TabNZConfig())
    assert client.config.use_fixture
    meetings = client.list_meetings()
    assert "data" in meetings
    assert meetings["data"]["meetings"][0]["name"] == "Ellerslie"


def test_tabnz_leakage_guard_rejects_post_off_snapshot():
    payload = __import__("json").loads(FIXTURE.read_text())["race_response"]
    ingested = parse_tabnz_race_payload(payload)
    start = ingested.race.start_time_utc

    bad = list(ingested.snapshots) + [
        ingested.snapshots[0].__class__(
            runner_id="nz-1001",
            back_price=99.0,
            lay_price=99.0,
            last_traded=99.0,
            traded_volume=0.0,
            ladder=[],
            timestamp_utc=start + 10,
        )
    ]
    with pytest.raises(ValueError, match="Leakage detected"):
        validate_snapshots_at_cutoff(bad, start)
