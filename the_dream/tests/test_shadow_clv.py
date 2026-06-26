"""End-to-end shadow CLV harness on historical data (no live API)."""

from pathlib import Path

from the_dream.backtest.metrics import metrics_report, write_clv_report
from the_dream.backtest.shadow_clv import ShadowCLVHarness
from the_dream.config import DreamConfig


DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "historical"


def test_shadow_clv_harness_end_to_end(tmp_path):
    cfg = DreamConfig(ev_threshold=0.001)
    harness = ShadowCLVHarness(cfg=cfg)
    report = harness.run_paths([DATA_DIR / "sample_races.jsonl"])

    assert report.n_races > 0
    assert report.null_mean_clv_prob is not None
    assert report.clv_above_null is not None
    assert report.clv_t_stat is not None

    out = tmp_path / "CLV_REPORT.json"
    write_clv_report(report, out)
    assert out.exists()
    assert "null_mean_clv_prob" in out.read_text()

    summary = metrics_report(report)
    assert "CLV ABOVE NULL" in summary
    assert "Null baseline CLV" in summary
