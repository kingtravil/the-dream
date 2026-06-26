"""Known-answer CLV oracle regression — proves detector has power and true zero."""

from clv_oracle import run_all_oracles

NULL_TOL_PP = 0.0005   # 0.05pp
NO_EDGE_TOL_PP = 0.003  # 0.3pp
INFORMED_MIN_PP = 0.01  # 1.0pp


def test_oracle_null_baseline_near_zero():
    results = run_all_oracles(n_races=2000)
    for key, r in results.items():
        assert abs(r.null_mean_clv) < NULL_TOL_PP, (
            f"{key}: null CLV {r.null_mean_clv * 100:.4f}pp should be ~0"
        )


def test_oracle_no_edge_clv_above_null_near_zero():
    results = run_all_oracles(n_races=2000)
    r = results["no_edge"]
    assert abs(r.clv_above_null) < NO_EDGE_TOL_PP, (
        f"no-edge CLV-above-null {r.clv_above_null * 100:.4f}pp should be ~0"
    )


def test_oracle_informed_clv_above_null_clearly_positive():
    results = run_all_oracles(n_races=2000)
    r = results["informed"]
    assert r.clv_above_null > INFORMED_MIN_PP, (
        f"informed CLV-above-null {r.clv_above_null * 100:.4f}pp should be > 1.0pp"
    )
    assert r.clv_t_stat > 20, f"informed t-stat {r.clv_t_stat:.1f} should be > 20"
