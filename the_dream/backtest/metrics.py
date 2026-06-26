"""Backtest metrics — CLV first, ROI second."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from the_dream.audit.ledger import AuditLedger
from the_dream.normalize.schema import BetRecord


@dataclass
class BacktestMetrics:
    n_bets: int
    n_no_bets: int
    mean_clv_prob: Optional[float]
    mean_clv_pct: Optional[float]
    clv_t_stat: Optional[float]
    roi_net: Optional[float]
    max_drawdown: Optional[float]
    brier_score: Optional[float]


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _t_stat(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    m = _mean(values)
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    if var <= 0:
        return None
    return m / math.sqrt(var / len(values))


def compute_metrics(ledger: AuditLedger) -> BacktestMetrics:
    bets = [r for r in ledger.records if r.decision == "BET" and r.stake > 0]
    no_bets = [r for r in ledger.records if r.decision == "NO_BET"]

    clv_probs = [r.clv_prob for r in bets if r.clv_prob is not None]
    clv_pcts = [r.clv_pct for r in bets if r.clv_pct is not None]

    total_staked = sum(r.stake for r in bets)
    total_pnl = sum(r.pnl_net for r in bets if r.pnl_net is not None)
    roi = (total_pnl / total_staked) if total_staked > 0 else None

    # Brier on settled bets with known outcomes
    brier_samples = [
        (r.p_model_entry, 1.0 if r.result == "WIN" else 0.0)
        for r in bets
        if r.result is not None
    ]
    brier = None
    if brier_samples:
        brier = _mean([(p - o) ** 2 for p, o in brier_samples])

    return BacktestMetrics(
        n_bets=len(bets),
        n_no_bets=len(no_bets),
        mean_clv_prob=_mean(clv_probs) if clv_probs else None,
        mean_clv_pct=_mean(clv_pcts) if clv_pcts else None,
        clv_t_stat=_t_stat(clv_probs),
        roi_net=roi,
        max_drawdown=None,
        brier_score=brier,
    )


def metrics_report(metrics: BacktestMetrics) -> str:
    lines = [
        "=== THE DREAM Backtest Metrics ===",
        f"Bets: {metrics.n_bets} | NO_BETs logged: {metrics.n_no_bets}",
    ]
    if metrics.mean_clv_prob is not None:
        lines.append(f"Mean CLV (prob): {metrics.mean_clv_prob:.4f}")
    if metrics.mean_clv_pct is not None:
        lines.append(f"Mean CLV (pct):  {metrics.mean_clv_pct:.4f}")
    if metrics.clv_t_stat is not None:
        lines.append(f"CLV t-stat:      {metrics.clv_t_stat:.2f}")
    if metrics.roi_net is not None:
        lines.append(f"ROI (net):       {metrics.roi_net:.2%}")
    if metrics.brier_score is not None:
        lines.append(f"Brier score:     {metrics.brier_score:.4f}")
    return "\n".join(lines)
