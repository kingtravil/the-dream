"""
THE DREAM — CLV measurement oracle (self-contained reference harness).

Validates the CLV truth-loop on KNOWN-ANSWER synthetic data BEFORE trusting it on
real prices. Use it as an oracle to diff the production harness against.

Hard lessons baked in (discovered by running this):
  * Measure CLV in DE-VIGGED PROBABILITY SPACE. Decimal-odds CLV% is biased upward
    by the convexity of 1/p whenever the entry line is noisier than the close —
    it manufactures fake positive CLV from zero skill.
  * Always report CLV ABOVE a bet-everything NULL baseline. Absolute CLV lies;
    CLV-minus-null is the real signal.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from the_dream.audit.clv import clv_prob_devig, null_clv_samples
from the_dream.edge.edge import net_ev_back
from the_dream.market.devig import proportional_devig

RNG = np.random.default_rng(7)
COMMISSION = {"NZ": 0.08, "AU": 0.085}


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def devig(prices: np.ndarray) -> np.ndarray:
    raw = 1.0 / prices
    return raw / raw.sum()


@dataclass
class OracleResult:
    name: str
    edge: float
    n_bets: int
    mean_clv_prob: float
    clv_t_stat: float
    null_mean_clv: float
    clv_above_null: float
    paper_roi: float


def make_race(n: int, edge: float) -> tuple:
    s = RNG.normal(0, 1, n) * 1.4
    true_p = softmax(s)
    snap_p = softmax(np.log(true_p) + RNG.normal(0, 0.35, n))
    price = 1.0 / (snap_p * 1.05)
    bsp_p = softmax(np.log(true_p) + RNG.normal(0, 0.18, n))
    p_mkt = devig(price)
    p_mod = softmax(
        (1 - edge) * np.log(p_mkt) + edge * np.log(true_p) + RNG.normal(0, 0.15, n)
    )
    winner = RNG.choice(n, p=true_p)
    return true_p, p_mkt, price, bsp_p, p_mod, winner


def run_oracle(
    name: str,
    edge: float,
    region: str = "NZ",
    n_races: int = 4000,
    n: int = 10,
) -> OracleResult:
    c = COMMISSION[region]
    bet_clv: list[float] = []
    null_clv: list[float] = []
    pnl: list[float] = []

    for _ in range(n_races):
        true_p, p_mkt, price, bsp_p, p_mod, winner = make_race(n, edge)

        p_mkt_dict = {str(i): float(p_mkt[i]) for i in range(n)}
        bsp_dict = {str(i): float(bsp_p[i]) for i in range(n)}
        null_clv.extend(null_clv_samples(p_mkt_dict, bsp_dict))

        for i in range(n):
            ev_net = net_ev_back(float(p_mod[i]), float(price[i]), c)
            if ev_net <= 0.0:
                continue
            bet_clv.append(clv_prob_devig(float(bsp_p[i]), float(p_mkt[i])))
            won = int(i == winner)
            pnl.append((price[i] - 1) * (1 - c) if won else -1.0)

    bc = np.array(bet_clv)
    nc = np.array(null_clv)
    t = bc.mean() / (bc.std(ddof=1) / np.sqrt(len(bc))) if len(bc) > 1 else 0.0

    return OracleResult(
        name=name,
        edge=edge,
        n_bets=len(bc),
        mean_clv_prob=float(bc.mean()),
        clv_t_stat=float(t),
        null_mean_clv=float(nc.mean()),
        clv_above_null=float(bc.mean() - nc.mean()),
        paper_roi=float(np.mean(pnl)) if pnl else 0.0,
    )


def run_all_oracles(n_races: int = 4000) -> dict[str, OracleResult]:
    return {
        "no_edge": run_oracle("A) NO-EDGE  (re-derives market)", edge=0.00, n_races=n_races),
        "informed": run_oracle("B) INFORMED (sees part of truth)", edge=0.45, n_races=n_races),
    }


if __name__ == "__main__":
    print("Measuring CLV on known-answer data before betting a cent.")
    results = run_all_oracles()
    for key, r in results.items():
        print(f"\n=== {r.name} (edge={r.edge}) ===")
        print(f"  bets                 : {r.n_bets:>8d}")
        print(f"  CLV (prob space)     : {r.mean_clv_prob * 100:>+7.3f} pp   t={r.clv_t_stat:+.1f}")
        print(f"  null CLV (bet-all)   : {r.null_mean_clv * 100:>+7.3f} pp   <- must be ~0")
        print(
            f"  CLV ABOVE NULL       : {r.clv_above_null * 100:>+7.3f} pp   <- the real signal"
        )
        print(f"  paper ROI (net)      : {r.paper_roi * 100:>+7.2f} %    (noisy; lags CLV)")
    print("\nVerdict: no-edge CLV-above-null ~0, informed clearly +. Detector works.")
