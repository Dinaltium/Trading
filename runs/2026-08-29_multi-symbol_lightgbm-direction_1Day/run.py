"""
Multi-symbol backtest of the production direction-signal logic (src/signals/direction.py's
feature/label definition), walk-forward retrained to avoid look-ahead bias, run per-symbol
in isolation. See notes.md for the full confirmed interpretation.

Reads raw/bars_<SYMBOL>.json (fetched via Alpaca CLI), writes all contract artifacts to
this run folder.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
import lightgbm as lgb

RUN_DIR = Path(__file__).resolve().parent
SYMBOLS = ["SPY", "QQQ", "DIA", "IWM", "AAPL", "TSLA"]

FEATURES = ["return_1d", "return_5d", "volatility_10d", "sma_ratio", "rsi_14"]
FORWARD_DAYS = 3
FORWARD_THRESHOLD = 0.005
ENTRY_THRESHOLD = 0.56
HOLD_DAYS = 3
SLIPPAGE_BPS = 5
INITIAL_CASH = 100_000.0
RETRAIN_EVERY = 60      # trading days between retrains
INITIAL_TRAIN_DAYS = 250  # warmup before the first walk-forward window


def load_bars(symbol: str) -> pd.DataFrame:
    data = json.loads((RUN_DIR / "raw" / f"bars_{symbol}.json").read_text())
    df = pd.DataFrame(data["bars"])
    df["t"] = pd.to_datetime(df["t"])
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df = df.sort_values("t").reset_index(drop=True)
    return df[["t", "open", "high", "low", "close", "volume"]]


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
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


def walk_forward_predict(feat: pd.DataFrame) -> pd.Series:
    """Returns a Series of P(Up), index-aligned with feat, NaN where no prediction was
    made (warmup period, or a row missing feature/label history at train time)."""
    n = len(feat)
    p_up = pd.Series(np.nan, index=feat.index)

    train_end = INITIAL_TRAIN_DAYS
    while train_end < n:
        test_end = min(train_end + RETRAIN_EVERY, n)

        train_slice = feat.iloc[:train_end].dropna(subset=FEATURES + ["target"])
        test_slice = feat.iloc[train_end:test_end]

        if len(train_slice) >= 60 and train_slice["target"].nunique() == 2:
            base_model = lgb.LGBMClassifier(
                objective="binary", learning_rate=0.05, num_leaves=15,
                n_estimators=100, min_child_samples=10, verbosity=-1, random_state=42,
            )
            calibrated = CalibratedClassifierCV(base_model, method="isotonic", cv=3)
            calibrated.fit(train_slice[FEATURES], train_slice["target"])

            test_X = test_slice[FEATURES]
            valid_mask = ~test_X.isnull().any(axis=1)
            if valid_mask.any():
                preds = calibrated.predict_proba(test_X[valid_mask])[:, 1]
                p_up.loc[test_X[valid_mask].index] = preds

        train_end = test_end

    return p_up


def simulate_trades(df: pd.DataFrame, p_up: pd.Series, symbol: str):
    """Enter next day's open when p_up[t] >= ENTRY_THRESHOLD (signal on close t, fill
    open t+1 — next_open fill model). Hold HOLD_DAYS trading days, exit at that day's open.
    No overlapping positions. Long-only, matches production (bearish signal maps to a put
    spread in the real system, not a short stock position here)."""
    trades = []
    equity_curve = []
    cash = INITIAL_CASH
    shares = 0.0
    position_exit_idx = None
    slip = SLIPPAGE_BPS / 10_000.0

    for i in range(len(df) - 1):
        row = df.iloc[i]
        equity = cash if shares == 0 else shares * row["close"]
        equity_curve.append({"t": row["t"], "equity": equity})

        if shares > 0 and i == position_exit_idx:
            fill = df.iloc[i + 1]["open"] * (1 - slip)
            proceeds = shares * fill
            trades[-1].update({
                "exit_time": df.iloc[i + 1]["t"].isoformat(),
                "exit_price": fill,
                "pnl": proceeds - trades[-1]["cost"],
                "return_pct": (proceeds - trades[-1]["cost"]) / trades[-1]["cost"],
            })
            cash += proceeds
            shares = 0.0
            position_exit_idx = None
            continue

        if shares == 0 and position_exit_idx is None:
            signal = p_up.iloc[i]
            if pd.notna(signal) and signal >= ENTRY_THRESHOLD:
                fill = df.iloc[i + 1]["open"] * (1 + slip)
                shares = cash / fill
                cost = shares * fill
                trades.append({
                    "symbol": symbol,
                    "entry_time": df.iloc[i + 1]["t"].isoformat(),
                    "entry_price": fill,
                    "p_up_signal": float(signal),
                    "cost": cost,
                })
                cash = 0.0
                position_exit_idx = i + 1 + HOLD_DAYS

    last = df.iloc[-1]
    final_equity = cash if shares == 0 else shares * last["close"]
    equity_curve.append({"t": last["t"], "equity": final_equity})

    completed_trades = [t for t in trades if "exit_time" in t]
    return completed_trades, pd.DataFrame(equity_curve)


def compute_metrics(equity_df: pd.DataFrame, trades: list) -> dict:
    equity_df = equity_df.copy()
    equity_df["ret"] = equity_df["equity"].pct_change()
    total_return = equity_df["equity"].iloc[-1] / equity_df["equity"].iloc[0] - 1.0

    n_days = (equity_df["t"].iloc[-1] - equity_df["t"].iloc[0]).days
    years = max(n_days / 365.25, 1e-9)
    ann_return = (1 + total_return) ** (1 / years) - 1.0

    running_max = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - running_max) / running_max
    max_drawdown = drawdown.min()

    daily_rets = equity_df["ret"].dropna()
    sharpe = (
        (daily_rets.mean() / daily_rets.std(ddof=1)) * math.sqrt(252)
        if daily_rets.std(ddof=1) > 0 else 0.0
    )

    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    return {
        "total_return_pct": round(total_return * 100, 3),
        "annualized_return_pct": round(ann_return * 100, 3),
        "max_drawdown_pct": round(max_drawdown * 100, 3),
        "sharpe": round(sharpe, 3),
        "n_trades": len(trades),
        "win_rate_pct": round(win_rate * 100, 2),
        "profit_factor": round(profit_factor, 3) if math.isfinite(profit_factor) else None,
        "final_equity": round(equity_df["equity"].iloc[-1], 2),
    }


def benchmark_buy_and_hold(df: pd.DataFrame) -> pd.DataFrame:
    entry = df.iloc[0]["open"]
    shares = INITIAL_CASH / entry
    return pd.DataFrame({"t": df["t"], "equity": df["close"] * shares})


def main():
    results = {}
    warnings = []

    for symbol in SYMBOLS:
        df = load_bars(symbol)
        feat = compute_features(df)
        p_up = walk_forward_predict(feat)

        trades, equity_df = simulate_trades(df, p_up, symbol)
        bench_df = benchmark_buy_and_hold(df)

        strat_metrics = compute_metrics(equity_df, trades)
        bench_trades_proxy = [{"pnl": bench_df["equity"].iloc[-1] - bench_df["equity"].iloc[0]}]
        bench_metrics = compute_metrics(bench_df, bench_trades_proxy)

        if not trades:
            warnings.append(f"{symbol}: zero trades executed — signal never crossed {ENTRY_THRESHOLD} threshold in the walk-forward test windows")

        results[symbol] = {"strategy": strat_metrics, "benchmark": bench_metrics, "trades": trades}

        pd.DataFrame(trades).to_csv(RUN_DIR / f"trades_{symbol}.csv", index=False)
        equity_df.to_csv(RUN_DIR / f"equity_{symbol}.csv", index=False)
        bench_df.to_csv(RUN_DIR / f"benchmark_equity_{symbol}.csv", index=False)

        print(f"{symbol}: {strat_metrics['n_trades']} trades, "
              f"total_return={strat_metrics['total_return_pct']}% "
              f"(bench {bench_metrics['total_return_pct']}%), "
              f"sharpe={strat_metrics['sharpe']} (bench {bench_metrics['sharpe']}), "
              f"win_rate={strat_metrics['win_rate_pct']}%")

    summary = {sym: {"strategy": r["strategy"], "benchmark": r["benchmark"]} for sym, r in results.items()}
    (RUN_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    (RUN_DIR / "warnings.json").write_text(json.dumps(warnings, indent=2))

    return results


if __name__ == "__main__":
    main()
