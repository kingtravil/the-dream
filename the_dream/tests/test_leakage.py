"""Feature leakage tests — must be able to FAIL on injected violations."""

import pytest

from the_dream.features import (
    assert_no_leakage,
    build_race_features,
    decision_cutoff,
    renormalize_after_scratch,
    validate_snapshots_at_cutoff,
)
from the_dream.features.horse import horse_features
from the_dream.features.market import market_features
from the_dream.ingest.form import FormRun, FormStore
from the_dream.normalize.schema import MarketSnapshot, RaceEvent, Runner


def test_decision_cutoff_before_off():
    start = 1_700_000_000
    cutoff = decision_cutoff(start, 120)
    assert cutoff == start - 120


def test_no_leakage_passes():
    assert_no_leakage({"form": 1_699_999_000}, 1_700_000_000)


def test_no_leakage_fails():
    with pytest.raises(ValueError, match="Leakage detected"):
        assert_no_leakage({"form": 1_700_000_100}, 1_700_000_000)


def test_horse_features_respect_cutoff():
    race = RaceEvent(
        race_id="r1",
        track="Randwick",
        distance_m=1400,
        condition="Good4",
        start_time_utc=1_700_000_000,
        runners=[Runner("R1", "H1", "J1", "T1", 5, 57.0)],
    )
    cutoff = decision_cutoff(race.start_time_utc, 120)
    future_run = FormRun("H1", cutoff + 1000, 1, 1400, "Randwick", "Good4", 57, "J1", "T1", 5, 4.0)
    past_run = FormRun("H1", cutoff - 86400, 2, 1400, "Randwick", "Good4", 57, "J1", "T1", 5, 6.0)

    feats = horse_features(race.runners[0], race, [future_run, past_run], cutoff)
    assert feats["avg_form_last_3"] > 0
    feats_only_past = horse_features(race.runners[0], race, [past_run], cutoff)
    assert feats_only_past["days_since_run"] == pytest.approx(1.0, abs=0.1)


def test_post_off_snapshot_rejected_in_validate():
    cutoff = 1_700_000_000
    snap = MarketSnapshot("R1", 3.0, 3.1, 3.0, 1000, [], cutoff + 1)
    with pytest.raises(ValueError, match="Leakage detected"):
        validate_snapshots_at_cutoff([snap], cutoff)


def test_post_off_snapshot_rejected_in_build_features():
    start = 1_700_000_000
    cutoff = decision_cutoff(start, 120)
    race = RaceEvent(
        race_id="r1",
        track="Randwick",
        distance_m=1400,
        condition="Good4",
        start_time_utc=start,
        runners=[Runner("R1", "H1", "J1", "T1", 5, 57.0)],
    )
    bad_snap = MarketSnapshot("R1", 3.0, 3.1, 3.0, 1000, [], cutoff + 60)
    with pytest.raises(ValueError, match="Leakage detected"):
        build_race_features(race, [bad_snap], FormStore(), 120)


def test_post_off_price_in_market_features_errors():
    cutoff = 1_700_000_000
    snap = MarketSnapshot("R1", 3.0, 3.1, 3.0, 1000, [], cutoff + 500)
    with pytest.raises(ValueError, match="Leakage detected"):
        market_features(snap, decision_cutoff_utc=cutoff)


def test_scratching_renormalizes_book():
    p_model = {"R1": 0.4, "R2": 0.35, "R3": 0.25}
    p_market = {"R1": 0.45, "R2": 0.35, "R3": 0.20}

    new_model, new_market = renormalize_after_scratch(p_model, p_market, ["R3"])

    assert "R3" not in new_model
    assert "R3" not in new_market
    assert abs(sum(new_model.values()) - 1.0) < 1e-9
    assert abs(sum(new_market.values()) - 1.0) < 1e-9
    assert new_market["R1"] > p_market["R1"]
