"""Commission-adjusted edge and CLV calculations."""

import pytest

from the_dream.audit.clv import clv_pct, clv_prob_devig, clv_prob_raw, null_clv_samples
from the_dream.edge.edge import net_ev_back
from the_dream.market.devig import proportional_devig


def test_proportional_devig_sums_to_one():
    probs = proportional_devig({"R1": 2.0, "R2": 4.0, "R3": 8.0})
    assert abs(sum(probs.values()) - 1.0) < 1e-9


def test_net_ev_negative_after_commission():
    p_model = 0.26
    price = 4.0
    ev = net_ev_back(p_model, price, commission=0.08)
    raw_implied = 0.25
    assert p_model - raw_implied > 0
    assert ev < 0


def test_net_ev_positive_when_edge_large_enough():
    ev = net_ev_back(0.35, 5.0, commission=0.08)
    assert ev > 0


def test_clv_prob_devig_positive_when_beat_close():
    """Primary metric: de-vigged prob space."""
    bsp_prob = 0.30
    p_market_entry = 0.25
    assert clv_prob_devig(bsp_prob, p_market_entry) > 0


def test_clv_raw_and_pct_positive_when_price_entry_gt_bsp():
    assert clv_prob_raw(price_entry=4.0, bsp=3.0) > 0
    assert clv_pct(price_entry=4.0, bsp=3.0) > 0


def test_clv_negative_when_worse_than_close():
    assert clv_prob_devig(0.20, 0.25) < 0
    assert clv_pct(price_entry=3.0, bsp=4.0) < 0


def test_null_baseline_zero_on_symmetric_field():
    p_market = {"R1": 0.25, "R2": 0.25, "R3": 0.25, "R4": 0.25}
    bsp_probs = {"R1": 0.25, "R2": 0.25, "R3": 0.25, "R4": 0.25}
    null = null_clv_samples(p_market, bsp_probs)
    assert abs(sum(null) / len(null)) < 1e-9


def test_settle_pnl_commission_on_winnings_only():
    from the_dream.audit.clv import settle_pnl

    gross, comm, net = settle_pnl(100.0, 5.0, won=True, commission=0.08)
    assert gross == 400.0
    assert comm == pytest.approx(32.0)
    assert net == pytest.approx(368.0)
