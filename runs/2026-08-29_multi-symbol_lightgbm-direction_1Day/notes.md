# Notes — Multi-Symbol Direction Signal Backtest

## Original request

User asked, while markets were closed over the hackathon weekend: "try with different markets and see how they perform." Prior conversation (with a separate Claude chat, logged in BRAINSTORM.md) had already scoped this correctly: backtest broadly across underlyings for research/validation, but keep the actual live-tradeable universe restricted to SPY/QQQ (or other index ETFs) to preserve the earnings-risk-free property those symbols give for free.

## Confirmed interpretation

Presented to the user and confirmed before running:

- Symbols: SPY, QQQ (current live set), DIA, IWM (other index ETFs, earnings-safe candidates), AAPL, TSLA (individual names, for contrast only — not live-trading candidates)
- Signal: exact feature/label definition from `src/signals/direction.py` — return_1d, return_5d, volatility_10d, sma_ratio, rsi_14; label = 3-day forward return > 0.5%
- Model: LightGBM, isotonic-calibrated, walk-forward retrained every 60 trading days (not a single fit-and-test, to avoid look-ahead)
- Entry: P(Up) >= 0.56 (matches production's bullish threshold), fill next-day open
- Exit: fixed 3-day hold (matches the label's own forward horizon), fill at exit day's open
- Timeframe: 2023-01-01 to 2026-08-28 daily bars
- Benchmark: buy-and-hold, same symbol

## Why this isn't a full options-strategy backtest

The `alpaca-trading-backtest` skill's fill-model machinery (next_open, quote-aware, etc.) is built for equity-style strategies. The production system trades defined-risk options spreads, which would need explicit contract-level historical fills — and Alpaca's historical option data is snapshot-only (confirmed empirically earlier this session: `OptionBarsRequest` returns OHLCV with no implied_volatility field, no way to reconstruct historical spread pricing cleanly in the time available). Scoped this backtest instead to validate the **direction signal's quality** as an equity proxy — a legitimate, much cheaper research question that still answers "is SPY/QQQ actually where the edge is, or did we just pick two tickers and not check."

## Indicator definitions

Identical to production, restated here for auditability:

```python
return_1d = close.pct_change(1)
return_5d = close.pct_change(5)
volatility_10d = return_1d.rolling(10).std()
sma_ratio = close / close.rolling(20).mean()
rsi_14 = 100 - (100 / (1 + gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)))
target = (close.shift(-3) / close - 1.0) > 0.005
```

## Fill model

`next_open`: signal computed on bar T's close, filled at bar T+1's open, +/-5bps slippage. Chosen because it's the skill's documented default and avoids same-bar look-ahead (deciding and filling on the same closing price would be unrealistic — you can't trade at a close you're simultaneously using to generate the signal).

## Dividend and split treatment

`adjustment=split` via Alpaca CLI — corrects for stock splits, does not reinvest dividends. Not corrected further; documented as a caveat in report.md (understates buy-and-hold benchmark slightly, conservative direction).

## Fee model

Not modeled. See `fee_source.json` for reasoning (commission-free equities, and not directly applicable since the real system trades options spreads).

## Calendar handling

No explicit holiday/weekend filtering — Alpaca's daily bars endpoint only returns actual trading days by construction, so no synthetic non-trading-day rows exist to filter.

## Look-ahead bias mitigation

Walk-forward retraining is the core defense here: at any point in the test set, the model was trained only on data strictly before that window. The alternative (fit once on the whole history, test on the whole history) would silently overstate performance since the model would have "seen the future" relative to early trades.

## Overfitting / repeated-variant risk

This is a single run with fixed hyperparameters (matching production exactly) — no parameter sweep was performed, so there's no multiple-comparisons overfitting risk from this backtest itself. If future work tunes the entry threshold, retrain cadence, or hold period based on this data, that tuning should be validated on a further out-of-sample period, not this same 2023-2026 window.

## Survivorship bias

All 6 symbols are large, currently-listed, liquid instruments that existed for the entire test window — no survivorship bias concern for this particular universe.

## Disclosures

> **Important disclosure**
> This backtest is a hypothetical historical simulation and does not represent actual trading performance. Backtested results do not guarantee future results. Results depend on market-data quality, data feed selection, corporate-action handling, fees, slippage, liquidity, taxes, execution assumptions, and implementation details. This material is for research and educational purposes only and is not investment advice, a recommendation, an offer, or a solicitation to buy or sell securities, options, cryptocurrencies, or any other financial product. All investments involve risk and may lose value. Review Alpaca's disclosures and agreements at [alpaca.markets/disclosures](https://alpaca.markets/disclosures).

Fee schedule reference (not directly applicable, kept for completeness): https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf
