"""Feature leakage tests — non-negotiable per spec §6."""

from the_dream.features import assert_no_leakage, decision_cutoff
from the_dream.features.horse import horse_features
from the_dream.ingest.form import FormRun
from the_dream.normalize.schema import RaceEvent, Runner
import pytest


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
    # Only past run should contribute
    feats_only_past = horse_features(race.runners[0], race, [past_run], cutoff)
    assert feats_only_past["days_since_run"] == pytest.approx(1.0, abs=0.1)
