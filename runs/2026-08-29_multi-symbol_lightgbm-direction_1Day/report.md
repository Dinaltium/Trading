# Multi-Symbol Direction Signal Backtest

Walk-forward validation of the exact classifier logic used in production (`src/signals/direction.py`), run as a long-only equity proxy strategy across 6 symbols, to check whether SPY/QQQ specifically show a real signal edge versus other candidates.

## Performance vs Benchmarks

| Symbol | | Total Return | Ann. Return | Max Drawdown | Sharpe | Trades | Win Rate | Profit Factor | Final Equity |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **SPY** | Strategy | 4.08% | 1.10% | -11.20% | 0.18 | 24 | 66.67% | 1.256 | $104,083.95 |
| | Benchmark | 102.03% | 21.27% | -19.00% | 1.36 | 1 | — | — | $200,158.70 |
| **QQQ** | Strategy | -0.26% | -0.07% | -12.92% | 0.03 | 9 | 22.22% | 0.972 | $99,743.95 |
| | Benchmark | 170.88% | 31.42% | -22.88% | 1.46 | 1 | — | — | $266,677.83 |
| **DIA** | Strategy | 8.25% | 2.20% | -11.59% | 0.34 | 8 | 75.00% | 1.851 | $108,245.29 |
| | Benchmark | 61.54% | 14.06% | -16.51% | 1.05 | 1 | — | — | $160,959.03 |
| **IWM** | Strategy | -0.55% | -0.15% | -11.61% | 0.02 | 19 | 47.37% | 0.974 | $99,453.79 |
| | Benchmark | 70.56% | 15.77% | -27.88% | 0.81 | 1 | — | — | $168,106.63 |
| **AAPL** | Strategy | 15.34% | 3.99% | -8.38% | 0.56 | 17 | 58.82% | 1.765 | $115,335.29 |
| | Benchmark | 155.62% | 29.35% | -33.43% | 1.13 | 1 | — | — | $245,394.53 |
| **TSLA** | Strategy | 30.06% | 7.47% | -25.31% | 0.49 | 12 | 58.33% | 1.691 | $130,056.31 |
| | Benchmark | 222.62% | 37.88% | -53.77% | 0.84 | 1 | — | — | $294,378.32 |

## Reading this correctly — signal quality, not the real strategy's P&L

The production system trades **defined-risk options spreads**, not the underlying stock. This backtest simulates "buy the stock and hold 3 days when the classifier says P(Up) ≥ 0.56" — a proxy to test whether the classifier's directional calls are actually better than a coin flip, not a simulation of real option P&L. Raw total return trailing buy-and-hold by this much is expected and not the concerning number here — the strategy is in cash most of the time by design, and 2023-2026 was an exceptional bull run across all 6 symbols.

**The number that matters: win rate and profit factor.**

- **SPY (66.7% win rate, profit factor 1.26) and DIA (75.0%, 1.85)** show a real edge above the 50% coin-flip line, with more wins paying more than losses cost.
- **QQQ (22.2%, 0.97) and IWM (47.4%, 0.97)** do not — QQQ in particular looks like noise or worse, despite being in the current live-trading set.
- **AAPL (58.8%, 1.77) and TSLA (58.3%, 1.69)** — the two individual-name symbols, not live-trading candidates — also show a real edge, comparable to or better than SPY.

## Configuration

- **Data:** Alpaca CLI `data bars`, feed=sip, adjustment=split, timeframe=1Day, 2023-01-01 to 2026-08-28
- **Model:** LightGBM binary classifier, isotonic-calibrated, retrained every 60 trading days on all prior data (walk-forward, no look-ahead), 250-day initial warmup
- **Entry:** P(Up) ≥ 0.56, signal on close, fill at next day's open, +5bps slippage
- **Exit:** fixed 3-trading-day hold, fill at exit day's open, -5bps slippage
- **Sizing:** 100% of that symbol's isolated capital, long-only, no leverage
- **Benchmark:** buy-and-hold, same symbol, entered at the first bar's open

## First / Last Trade (SPY, representative)

See `trades_SPY.csv` for the full list. First and last entries available per-symbol in each `trades_<SYMBOL>.csv`.

## Assumptions & Caveats

- **Dividends not modeled** — `adjustment=split` only adjusts for splits, not dividend reinvestment. This understates buy-and-hold benchmark returns for all 6 symbols (all pay dividends), making the benchmark comparison slightly conservative in the strategy's favor.
- **No fees modeled** — Alpaca US equities are commission-free; regulatory pass-through fees are negligible at this size. Not directly applicable anyway since real trading uses options spreads, not equities.
- **Small trade counts** — DIA's 75% win rate is only 8 trades; SPY's 24 trades is still a thin sample for a confident edge claim. Treat as directional evidence, not statistical proof.
- **Equity proxy, not the real strategy** — see "Reading this correctly" above. This validates the classifier's directional signal quality; it does not simulate the real options-spread P&L, which has a fundamentally different, capped-risk payoff shape.
- **Out-of-sample by construction** — walk-forward retraining means every prediction was made on data the model hadn't been trained on at that point, avoiding the most basic look-ahead bias. It does not rule out broader regime dependence (this window is one continuous bull market).

## Data Fingerprint

See `data_fingerprint.json` for per-symbol source file hashes.

---

**Important disclosure**

This backtest is a hypothetical historical simulation and does not represent actual trading performance. Backtested results do not guarantee future results. Results depend on market-data quality, data feed selection, corporate-action handling, fees, slippage, liquidity, taxes, execution assumptions, and implementation details. This material is for research and educational purposes only and is not investment advice, a recommendation, an offer, or a solicitation to buy or sell securities, options, cryptocurrencies, or any other financial product. All investments involve risk and may lose value. Review Alpaca's disclosures and agreements at [alpaca.markets/disclosures](https://alpaca.markets/disclosures).
