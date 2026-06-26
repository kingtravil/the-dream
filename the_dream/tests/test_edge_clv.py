"""Commission-adjusted edge and CLV calculations."""

import pytest

from the_dream.audit.clv import clv_percentage, clv_probability, settle_pnl
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


def test_clv_positive_when_beat_close():
    clv_p = clv_probability(p_market_entry=0.25, bsp=3.0, price_entry=4.0)
    clv_pc = clv_percentage(price_entry=4.0, bsp=3.0)
    assert clv_p > 0
    assert clv_pc > 0


def test_settle_pnl_commission_on_winnings_only():
    gross, comm, net = settle_pnl(100.0, 5.0, won=True, commission=0.08)
    assert gross == 400.0
    assert comm == pytest.approx(32.0)
    assert net == pytest.approx(368.0)
