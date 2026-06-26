# 🐎 THE DREAM

CLV-validated probabilistic racing-market engine for NZ/AU.

**North star:** Find prices that are wrong, bet them only when edge survives commission, and let **closing line value (CLV) vs Betfair BSP** — not last week's profit — tell you whether the system is actually good.

## Architecture

Modular monolith with a single pure `decide()` function shared by live and backtest paths (enforced by parity tests).

```
DATA INGESTION → NORMALIZATION → FEATURE ENGINE → PROBABILITY ENGINE
       │                                              │
       ▼                                              ▼
MARKET COMPARATOR (de-vig) ──────────────────▶ EDGE ENGINE (commission-adjusted)
                                                        │
                                         HUMAN SIGNAL OVERLAY (±15%)
                                                        │
                                                 DECISION ENGINE
                                                        │
                                          RISK + STAKING ENGINE
                                                        │
                                    EXECUTION (PAPER / LIVE_MICRO / LIVE)
                                                        │
                                          AUDIT + CLV TRACKING (BSP loop)
```

## Operating modes

| Mode | Purpose |
|------|---------|
| `PAPER` | Honest fills from ladder depth; no real money |
| `LIVE_MICRO` | Real bets at fixed tiny stakes |
| `LIVE` | Full fractional-Kelly staking |

Stay in `PAPER` until CLV is statistically positive over thousands of bets.

## Quick start

```bash
pip install -e ".[dev]"
pytest
python main.py --command shadow --mode PAPER --region NZ
python main.py --command shadow-clv --data data/historical/sample_races.jsonl
python clv_oracle.py
```

## CLV measurement

**Headline metric:** de-vigged probability-space CLV (`bsp_prob - p_market_entry_devig`), reported as **CLV-above-null** (minus the bet-everything null baseline). Decimal-odds `clv_pct` is display-only — biased upward by the convexity of 1/p.

| Command | Purpose |
|---------|---------|
| `python clv_oracle.py` | Known-answer regression on synthetic data |
| `python main.py --command shadow-clv` | Historical replay, stake nothing, emit `CLV_REPORT.json` |

## Key modules

| Path | Role |
|------|------|
| `the_dream/config.py` | Commission tables, risk limits, mode flags |
| `the_dream/decision/decide.py` | Pure decision function (live == backtest) |
| `the_dream/edge/edge.py` | Commission-adjusted net EV |
| `the_dream/audit/clv.py` | De-vig prob-space CLV + null baseline |
| `the_dream/backtest/shadow_clv.py` | Historical shadow CLV harness |
| `the_dream/ingest/historical.py` | Offline historical race loader |
| `clv_oracle.py` | Known-answer CLV regression oracle |
| `the_dream/tests/test_decide_parity.py` | Parity enforcement |

## Commission

NZ racing: **8%** Market Base Rate on net winnings. AU: **7–10%** by state/code. All edge gates use `ev_net`, not raw edge.

## Data sources

- **Primary:** Betfair Exchange (prices + BSP benchmark)
- **Secondary:** TAB (optional cross-check only — system runs on Betfair alone)
- **Form:** Historical runs for feature engineering

Wire Betfair credentials in `the_dream/ingest/betfair.py` when ready for live data.

## Success criteria

1. Mean CLV > 0 with significant t-stat over large sample
2. Risk-adjusted, commission-net returns stable under real execution
3. CLV first. Profit follows, eventually and noisily.
