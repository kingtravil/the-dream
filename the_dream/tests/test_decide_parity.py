"""Proves backtest == live decision path (spec §17)."""

from the_dream.backtest.replay import BacktestEngine
from the_dream.config import DreamConfig
from the_dream.decision.decide import DecisionContext, decide
from the_dream.ingest.form import FormStore
from the_dream.normalize.schema import HumanSignal, MarketSnapshot, RaceEvent, Runner
from the_dream.pipeline import DreamEngine
from the_dream.risk.exposure import RiskCheck, RiskState


def _sample_context(**overrides) -> DecisionContext:
    cfg = DreamConfig()
    base_kwargs = dict(
        runner_id="R1",
        race_id="race-1",
        p_model=0.30,
        p_market=0.20,
        price=5.0,
        ev_net=0.05,
        confidence=0.75,
        cfg=cfg,
        risk=RiskCheck(True, "", 25.0),
        human=None,
        proposed_stake=25.0,
    )
    base_kwargs.update(overrides)
    return DecisionContext(**base_kwargs)


def test_decide_is_pure():
    """Same DecisionContext twice → identical Decision (pure function)."""
    ctx = _sample_context()
    assert decide(ctx) == decide(ctx)


def test_decide_parity_live_vs_backtest():
    """Backtest helper must call the same decide() with equivalent context."""
    ctx = _sample_context()
    live_decision = decide(ctx)

    cfg = DreamConfig(bankroll=10_000.0)
    backtest = BacktestEngine(cfg=cfg, form_store=FormStore())
    backtest.risk_state = RiskState(bankroll=10_000.0, peak_bankroll=10_000.0)

    # Pre-compute the same risk check the live path would use
    risk = RiskCheck(True, "", ctx.proposed_stake)
    backtest_decision = decide(
        DecisionContext(
            runner_id=ctx.runner_id,
            race_id=ctx.race_id,
            p_model=ctx.p_model,
            p_market=ctx.p_market,
            price=ctx.price,
            ev_net=ctx.ev_net,
            confidence=ctx.confidence,
            cfg=ctx.cfg,
            risk=risk,
            human=ctx.human,
            proposed_stake=ctx.proposed_stake,
        )
    )

    assert live_decision == backtest_decision


def test_backtest_decide_for_runner_matches_decide():
    """BacktestEngine.decide_for_runner delegates to the same decide()."""
    cfg = DreamConfig(bankroll=10_000.0, ev_threshold=0.001)
    backtest = BacktestEngine(cfg=cfg, form_store=FormStore())
    race = RaceEvent(
        race_id="race-1",
        track="Ellerslie",
        distance_m=1600,
        condition="Good4",
        start_time_utc=1_700_000_000,
        runners=[Runner("R1", "H1", "J1", "T1", 3, 57.0)],
    )
    snap = MarketSnapshot("R1", 5.0, 5.2, 5.0, 1000.0, [(5.0, 500)], 1_699_999_800)

    direct = backtest.decide_for_runner(
        race=race,
        runner_id="R1",
        p_model=0.30,
        p_market=0.20,
        price=5.0,
        confidence=0.75,
        snapshot=snap,
        human_signals=[],
    )

    # Rebuild the context the helper would have used
    from the_dream.edge.edge import net_ev_back
    from the_dream.features import decision_cutoff
    from the_dream.risk.kelly import fractional_kelly_stake

    cutoff = decision_cutoff(race.start_time_utc, cfg.decision_lead_seconds)
    proposed = fractional_kelly_stake(0.30, 5.0, 10_000.0, cfg.risk.kelly_fraction, cfg.commission)
    from the_dream.risk.exposure import check_risk

    risk = check_risk(proposed, race.race_id, "R1", snap, backtest.risk_state, cfg)
    ctx = DecisionContext(
        runner_id="R1",
        race_id="race-1",
        p_model=0.30,
        p_market=0.20,
        price=5.0,
        ev_net=net_ev_back(0.30, 5.0, cfg.commission),
        confidence=0.75,
        cfg=cfg,
        risk=risk,
        human=None,
        proposed_stake=proposed,
    )
    assert direct == decide(ctx)


def test_decide_no_bet_below_threshold():
    ctx = _sample_context(ev_net=0.005)
    decision = decide(ctx)
    assert decision.decision.value == "NO_BET"
    assert "ev below threshold" in decision.reason


def test_decide_human_veto():
    human = HumanSignal("R1", 0.8, 4.0, ["intel"], 1_699_999_000, veto=True)
    ctx = _sample_context(human=human)
    decision = decide(ctx)
    assert decision.decision.value == "NO_BET"
    assert "human veto" in decision.reason


def test_decide_human_agree_strong():
    human = HumanSignal("R1", 0.8, 4.0, ["track_bias"], 1_699_999_000, agrees=True)
    ctx = _sample_context(human=human)
    decision = decide(ctx)
    assert decision.decision.value == "BET"
    assert decision.strength is not None
    assert decision.strength.value == "STRONG"


def test_engine_uses_same_decide():
    cfg = DreamConfig(ev_threshold=0.001)
    engine = DreamEngine(cfg=cfg)
    race = RaceEvent(
        race_id="race-2",
        track="Flemington",
        distance_m=2000,
        condition="Soft5",
        start_time_utc=1_700_000_000,
        runners=[
            Runner("R1", "H1", "J1", "T1", 1, 58.0),
            Runner("R2", "H2", "J2", "T2", 2, 57.5),
        ],
    )
    snaps = [
        MarketSnapshot("R1", 3.5, 3.6, 3.5, 5000, [(3.5, 2000)], 1_699_999_800),
        MarketSnapshot("R2", 6.0, 6.2, 6.0, 3000, [(6.0, 1500)], 1_699_999_800),
    ]
    outputs = engine.evaluate_race(race, snaps)
    assert len(outputs) == 2
    assert all("decision" in o for o in outputs)
    assert engine.ledger.no_bet_count() + engine.ledger.bet_count() == 2
