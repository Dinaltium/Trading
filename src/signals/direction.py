"""
Direction classifier: LightGBM on Alpaca daily bars, calibrated probability output.

Feeds classifier_win_probability into risk_gate.py's Kelly sizing (see risk_gate.py's
TradeProposal docstring) — this is the ONLY legitimate source for that number. Never
the LLM's self-reported confidence.

CRITICAL ORDERING BUG TO AVOID: compute features on the FULL bar history first, then
split off today's row (the one we actually want a prediction for) BEFORE dropping rows
with a missing forward-return label. Today's row has no label yet by definition (the
forward return needs future bars that don't exist), so if you dropna() before splitting
off "today", you silently lose the one row you actually needed to predict on.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
import lightgbm as lgb

from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

FEATURES = ["return_1d", "return_5d", "volatility_10d", "sma_ratio", "rsi_14"]
FORWARD_DAYS = 3          # predict sign of 3-day forward return
FORWARD_THRESHOLD = 0.005  # must move >0.5% to count as "up" — filters out noise-band moves


@dataclass
class DirectionSignal:
    underlying: str
    p_up: float                # calibrated P(3-day forward return > +0.5%)
    n_train_rows: int
    latest_close: float


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["return_1d"] = df["close"].pct_change(1)
    df["return_5d"] = df["close"].pct_change(5)
    df["volatility_10d"] = df["return_1d"].rolling(10).std()
    df["sma_ratio"] = df["close"] / df["close"].rolling(20).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    df["fwd_return"] = df["close"].shift(-FORWARD_DAYS) / df["close"] - 1.0
    df["target"] = (df["fwd_return"] > FORWARD_THRESHOLD).astype(int)
    return df


def fetch_daily_bars(client: StockHistoricalDataClient, underlying: str, lookback_days: int = 900) -> pd.DataFrame:
    req = StockBarsRequest(
        symbol_or_symbols=underlying,
        timeframe=TimeFrame.Day,
        start=datetime.now() - timedelta(days=lookback_days),
    )
    bars = client.get_stock_bars(req).df
    if bars.empty:
        return bars
    return bars.reset_index(level=0, drop=True) if "symbol" in bars.index.names else bars


def train_and_predict(client: StockHistoricalDataClient, underlying: str) -> Optional[DirectionSignal]:
    raw = fetch_daily_bars(client, underlying)
    if raw.empty or len(raw) < 80:
        return None

    feat = _compute_features(raw)

    # Split off "today" (features complete, target NaN by construction) BEFORE dropping
    # rows with a missing target — this is the ordering the module docstring warns about.
    latest_row = feat.iloc[[-1]]
    training_rows = feat.iloc[:-1].dropna(subset=FEATURES + ["target"])

    if len(training_rows) < 60:
        return None

    X_train = training_rows[FEATURES]
    y_train = training_rows["target"]

    if y_train.nunique() < 2:
        return None  # can't calibrate a classifier that's only ever seen one class

    base_model = lgb.LGBMClassifier(
        objective="binary",
        learning_rate=0.05,
        num_leaves=15,
        n_estimators=100,
        min_child_samples=10,
        verbosity=-1,
        random_state=42,
    )

    n_splits = 3 if len(training_rows) >= 150 else 2
    calibrated = CalibratedClassifierCV(base_model, method="isotonic", cv=n_splits)
    calibrated.fit(X_train, y_train)

    latest_X = latest_row[FEATURES]
    if latest_X.isnull().any(axis=None):
        return None  # not enough trailing history to compute today's rolling features

    p_up = float(calibrated.predict_proba(latest_X)[0][1])

    return DirectionSignal(
        underlying=underlying,
        p_up=round(p_up, 4),
        n_train_rows=len(training_rows),
        latest_close=float(latest_row["close"].iloc[0]),
    )


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=True)
    client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))

    for symbol in ["SPY", "QQQ"]:
        signal = train_and_predict(client, symbol)
        print(signal)
