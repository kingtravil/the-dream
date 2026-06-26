"""Backtest metrics — CLV first (de-vig prob space), CLV-above-null headline."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from the_dream.audit.ledger import AuditLedger
from the_dream.normalize.schema import BetRecord

NULL_BASELINE_TOLERANCE_PP = 0.0005  # 0.05 percentage points in prob space
NULL_FAIL_THRESHOLD_PP = 0.003  # 0.3pp for no-edge oracle check


@dataclass
class CalibrationBand:
    lo: float
    hi: float
    predicted_pct: float
    actual_pct: float
    n: int


@dataclass
class CLVReport:
    n_races: int
    n_would_be_bets: int
    n_no_bets: int
    mean_clv_prob: Optional[float]
    clv_t_stat: Optional[float]
    null_mean_clv_prob: Optional[float]
    clv_above_null: Optional[float]
    null_baseline_ok: bool
    mean_clv_pct: Optional[float]
    brier_score: Optional[float]
    calibration_by_band: List[CalibrationBand] = field(default_factory=list)
    slippage_placeholder: Optional[float] = None
    roi_net: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["calibration_by_band"] = [asdict(b) for b in self.calibration_by_band]
        return d


@dataclass
class BacktestMetrics:
    n_bets: int
    n_no_bets: int
    mean_clv_prob: Optional[float]
    mean_clv_pct: Optional[float]
    clv_t_stat: Optional[float]
    null_mean_clv_prob: Optional[float]
    clv_above_null: Optional[float]
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


def _calibration_bands(bets: List[BetRecord]) -> List[CalibrationBand]:
    bands = [(1, 3), (3, 6), (6, 12), (12, 1e9)]
    results: List[CalibrationBand] = []
    for lo, hi in bands:
        subset = [
            b for b in bets
            if lo <= b.price_entry < hi and b.result is not None
        ]
        if len(subset) < 30:
            continue
        pred = _mean([b.p_model_entry for b in subset])
        actual = _mean([1.0 if b.result == "WIN" else 0.0 for b in subset])
        results.append(
            CalibrationBand(
                lo=lo,
                hi=hi if hi < 1e8 else 999.0,
                predicted_pct=pred * 100,
                actual_pct=actual * 100,
                n=len(subset),
            )
        )
    return results


def build_clv_report(
    ledger: AuditLedger,
    null_clv_samples: List[float],
    n_races: Optional[int] = None,
) -> CLVReport:
    would_be = ledger.would_be_bets()
    no_bets = [r for r in ledger.records if r.decision == "NO_BET"]

    clv_probs = [r.clv_prob for r in would_be if r.clv_prob is not None]
    clv_pcts = [r.clv_pct for r in would_be if r.clv_pct is not None]

    null_mean = _mean(null_clv_samples) if null_clv_samples else None
    bet_mean = _mean(clv_probs) if clv_probs else None
    above_null = (bet_mean - null_mean) if bet_mean is not None and null_mean is not None else None

    null_ok = (
        null_mean is not None
        and abs(null_mean) < NULL_BASELINE_TOLERANCE_PP
    )

    race_ids = {r.race_id for r in ledger.records}

    return CLVReport(
        n_races=n_races if n_races is not None else len(race_ids),
        n_would_be_bets=len(would_be),
        n_no_bets=len(no_bets),
        mean_clv_prob=bet_mean,
        clv_t_stat=_t_stat(clv_probs),
        null_mean_clv_prob=null_mean,
        clv_above_null=above_null,
        null_baseline_ok=null_ok,
        mean_clv_pct=_mean(clv_pcts) if clv_pcts else None,
        brier_score=_compute_brier(would_be),
        calibration_by_band=_calibration_bands(
            [r for r in would_be if r.result is not None]
        ),
        slippage_placeholder=None,
    )


def _compute_brier(bets: List[BetRecord]) -> Optional[float]:
    samples = [
        (r.p_model_entry, 1.0 if r.result == "WIN" else 0.0)
        for r in bets
        if r.result is not None
    ]
    if not samples:
        return None
    return _mean([(p - o) ** 2 for p, o in samples])


def write_clv_report(report: CLVReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(report.to_dict(), f, indent=2)


def metrics_report(report: CLVReport | BacktestMetrics) -> str:
    if isinstance(report, BacktestMetrics):
        report = CLVReport(
            n_races=0,
            n_would_be_bets=report.n_bets,
            n_no_bets=report.n_no_bets,
            mean_clv_prob=report.mean_clv_prob,
            clv_t_stat=report.clv_t_stat,
            null_mean_clv_prob=report.null_mean_clv_prob,
            clv_above_null=report.clv_above_null,
            null_baseline_ok=(
                report.null_mean_clv_prob is not None
                and abs(report.null_mean_clv_prob) < NULL_BASELINE_TOLERANCE_PP
            ),
            mean_clv_pct=report.mean_clv_pct,
            brier_score=report.brier_score,
            roi_net=report.roi_net,
        )
    lines = [
        "=== THE DREAM CLV Report (de-vig prob space) ===",
        f"Races: {report.n_races} | Would-be bets: {report.n_would_be_bets} | NO_BETs: {report.n_no_bets}",
    ]
    if report.null_mean_clv_prob is not None:
        lines.append(
            f"Null baseline CLV:  {report.null_mean_clv_prob * 100:+.4f} pp"
            f"  {'OK' if report.null_baseline_ok else 'FAIL — pipeline broken'}"
        )
    if report.mean_clv_prob is not None:
        lines.append(f"Mean CLV (prob):    {report.mean_clv_prob * 100:+.4f} pp")
    if report.clv_above_null is not None:
        lines.append(f"CLV ABOVE NULL:     {report.clv_above_null * 100:+.4f} pp  <- headline")
    if report.clv_t_stat is not None:
        lines.append(f"CLV t-stat:          {report.clv_t_stat:+.2f}")
    if report.mean_clv_pct is not None:
        lines.append(f"Mean CLV (pct):     {report.mean_clv_pct * 100:+.2f}%  (display only)")
    if report.brier_score is not None:
        lines.append(f"Brier score:        {report.brier_score:.4f}")
    if report.calibration_by_band:
        lines.append("Calibration by odds band:")
        for band in report.calibration_by_band:
            hi = "+" if band.hi >= 999 else str(int(band.hi))
            lines.append(
                f"  {int(band.lo)}-{hi}: pred {band.predicted_pct:.1f}%  "
                f"actual {band.actual_pct:.1f}%  (n={band.n})"
            )
    return "\n".join(lines)


def compute_metrics(ledger: AuditLedger, null_clv_samples: Optional[List[float]] = None) -> BacktestMetrics:
    report = build_clv_report(ledger, null_clv_samples or [])
    bets = ledger.would_be_bets()
    total_staked = sum(r.stake for r in bets)
    total_pnl = sum(r.pnl_net for r in bets if r.pnl_net is not None)
    roi = (total_pnl / total_staked) if total_staked > 0 else None

    return BacktestMetrics(
        n_bets=report.n_would_be_bets,
        n_no_bets=report.n_no_bets,
        mean_clv_prob=report.mean_clv_prob,
        mean_clv_pct=report.mean_clv_pct,
        clv_t_stat=report.clv_t_stat,
        null_mean_clv_prob=report.null_mean_clv_prob,
        clv_above_null=report.clv_above_null,
        roi_net=roi,
        max_drawdown=None,
        brier_score=report.brier_score,
    )
