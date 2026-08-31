"""
Volatility signals: Volatility Risk Premium (VRP) and IV Rank/Percentile.

Alpaca's option chain/snapshot endpoint is a LIVE snapshot only — no historical IV lookup
(confirmed empirically: OptionBarsRequest returns OHLCV, no implied_volatility field).
See AGENTS.md 6b and BRAINSTORM.md section 5/7f for the research behind this.

Two signals, deliberately decoupled:
  - VRP: works from day 1, no history needed (current IV vs realized vol from stock bars).
  - IV Rank/Percentile: needs an accumulating log. Starts thin on day 1, more reliable
    each day of the hackathon. Every call to log_iv_snapshot() appends one row;
    iv_rank_from_log() reports its own sample size so callers (and the LLM prompt)
    can weight it honestly instead of pretending a 3-day lookback is a 52-week one.

Two properties this file has to get right, both learned the hard way (see the audit-log
forensics in BRAINSTORM.md):
  - The sample count is a count of CYCLES, not days. At a 15-minute cadence 68 rows is
    ~36 hours, not 68 days. It is named and reported as samples so nothing downstream
    can mistake it for a calendar lookback.
  - The current observation must NOT be inside the window it is ranked against. Logging
    first and ranking afterwards made every new high score exactly 100.0 by construction,
    which pinned iv_rank at its ceiling and jammed the regime flag permanently on.
"""

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


@dataclass
class VolSignals:
    underlying: str
    current_atm_iv: float
    realized_vol_20d: float
    vrp: float                        # current_atm_iv - realized_vol_20d, in vol points
    iv_rank: Optional[float]          # None if not enough logged history yet
    iv_percentile: Optional[float]
    iv_history_samples: int           # number of logged CYCLES backing iv_rank/iv_percentile.
                                      # Not days - at a 15-min cadence ~26 samples is one trading day.
    iv_history_days: int              # distinct calendar dates in that window.
    iv_rank_trusted: bool             # whether the window is deep enough to reason from.


def get_current_atm_iv(opt_client: OptionHistoricalDataClient, underlying: str, current_price: float) -> Optional[float]:
    """Pulls the live option chain and returns the IV of the near-term contract closest to ATM."""
    chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=underlying))
    if not chain:
        return None

    best_symbol, best_diff = None, float("inf")
    for symbol, snap in chain.items():
        if snap.implied_volatility is None:
            continue
        # OCC symbol strike is the last 8 digits / 1000, e.g. ...P00786000 -> 786.00
        strike = int(symbol[-8:]) / 1000.0
        diff = abs(strike - current_price)
        if diff < best_diff:
            best_diff, best_symbol = diff, symbol

    if best_symbol is None:
        return None
    return chain[best_symbol].implied_volatility


def realized_volatility(stock_client: StockHistoricalDataClient, underlying: str, window: int = 20) -> Optional[float]:
    """Annualized realized vol from daily log returns over the trailing `window` days."""
    req = StockBarsRequest(
        symbol_or_symbols=underlying,
        timeframe=TimeFrame.Day,
        start=datetime.now() - timedelta(days=window * 3),  # buffer for weekends/holidays
    )
    bars = stock_client.get_stock_bars(req).df
    if bars.empty or len(bars) < window + 1:
        return None
    closes = bars["close"].tail(window + 1).values
    log_returns = np.diff(np.log(closes))
    daily_std = np.std(log_returns, ddof=1)
    return float(daily_std * np.sqrt(252))


def log_iv_snapshot(underlying: str, iv: float, log_path: Optional[Path] = None) -> None:
    """Appends one row to logs/iv_history_<underlying>.csv. Call once per trading cycle."""
    log_path = log_path or LOG_DIR / f"iv_history_{underlying}.csv"
    is_new = not log_path.exists()
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "underlying", "atm_iv"])
        writer.writerow([datetime.utcnow().isoformat(), underlying, iv])


# A rank is a statement about "recent history". Two ways that statement can be hollow:
# too few observations, or plenty of observations that all landed inside a single session.
# The window that pinned iv_rank to 100 for four days was the second kind - 14 samples,
# every one of them stamped 2026-08-28. Depth in samples alone would have called it fine.
MIN_TRUSTED_SAMPLES = 30    # ~1.2 trading days at the 15-minute cadence
MIN_TRUSTED_DAYS = 2        # a single session's spread is not a history


def history_depth(underlying: str, log_path: Optional[Path] = None) -> tuple[int, int]:
    """Returns (sample_count, distinct_calendar_days) for the logged IV window."""
    log_path = log_path or LOG_DIR / f"iv_history_{underlying}.csv"
    if not log_path.exists():
        return 0, 0
    with open(log_path, "r") as f:
        rows = list(csv.DictReader(f))
    days = {r["timestamp"][:10] for r in rows if r.get("timestamp")}
    return len(rows), len(days)


def iv_rank_is_trusted(samples: int, days: int) -> bool:
    return samples >= MIN_TRUSTED_SAMPLES and days >= MIN_TRUSTED_DAYS


def iv_rank_from_log(underlying: str, current_iv: float, log_path: Optional[Path] = None) -> tuple[Optional[float], Optional[float], int]:
    """Returns (iv_rank, iv_percentile, sample_size) ranking current_iv against the PRIOR
    history on disk. Call this before log_iv_snapshot(), never after: if the current
    observation is already in the window, any new high scores exactly 100.0 and any new
    low exactly 0.0, regardless of what the market actually did.

    Returns (None, None, n) if fewer than 5 prior data points - too thin to mean anything.

    Note the 5 here is a floor for producing a number at all, NOT a threshold for believing
    it. A rank computed from a handful of samples is still returned, because returning None
    routes the rulebook straight to cash and stops the agent trading entirely. Whether the
    number is trustworthy is a separate question, answered by history_depth() below."""
    log_path = log_path or LOG_DIR / f"iv_history_{underlying}.csv"
    if not log_path.exists():
        return None, None, 0

    with open(log_path, "r") as f:
        rows = list(csv.DictReader(f))
    history = [float(r["atm_iv"]) for r in rows]
    n = len(history)
    if n < 5:
        return None, None, n

    lo, hi = min(history), max(history)
    if hi > lo:
        # Clamped because current_iv is deliberately outside the window: a genuine new
        # extreme would otherwise compute above 100 or below 0.
        iv_rank = min(100.0, max(0.0, (current_iv - lo) / (hi - lo) * 100.0))
    else:
        iv_rank = 50.0
    iv_percentile = (sum(1 for h in history if h < current_iv) / n) * 100.0
    return round(iv_rank, 2), round(iv_percentile, 2), n


def compute_vol_signals(
    opt_client: OptionHistoricalDataClient,
    stock_client: StockHistoricalDataClient,
    underlying: str,
    current_price: float,
    record_history: bool = False,
) -> Optional[VolSignals]:
    """record_history must be True ONLY on real market-hours cycles. It defaults to False
    so ad-hoc runs, dry runs and weekend soak tests can exercise the whole pipeline without
    writing into the IV history that iv_rank is measured against. A single stale
    closed-market quote appended here becomes the window's max and skews every subsequent
    rank for the rest of the competition."""
    current_iv = get_current_atm_iv(opt_client, underlying, current_price)
    if current_iv is None:
        return None

    realized_vol = realized_volatility(stock_client, underlying)
    if realized_vol is None:
        return None

    # Rank first, against prior history only - then append. Order matters, see iv_rank_from_log.
    iv_rank, iv_pct, n = iv_rank_from_log(underlying, current_iv)
    samples, days = history_depth(underlying)
    if record_history:
        log_iv_snapshot(underlying, current_iv)

    return VolSignals(
        underlying=underlying,
        current_atm_iv=round(current_iv, 4),
        realized_vol_20d=round(realized_vol, 4),
        vrp=round(current_iv - realized_vol, 4),
        iv_rank=iv_rank,
        iv_percentile=iv_pct,
        iv_history_samples=n,
        iv_history_days=days,
        iv_rank_trusted=iv_rank_is_trusted(samples, days),
    )


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=True)
    key, sec = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    opt_client = OptionHistoricalDataClient(key, sec)
    stock_client = StockHistoricalDataClient(key, sec)

    latest = stock_client.get_stock_bars(
        StockBarsRequest(symbol_or_symbols="SPY", timeframe=TimeFrame.Day, start=datetime.now() - timedelta(days=5))
    ).df
    price = float(latest["close"].iloc[-1])
    print(f"SPY current price: {price}")

    signals = compute_vol_signals(opt_client, stock_client, "SPY", price)
    print(signals)
