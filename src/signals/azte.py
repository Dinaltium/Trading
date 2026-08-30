"""
AZTE — Adaptive Z-score Trigger Engine.

From AGENTICAITA (arXiv:2605.12532), whose first architectural property is "selective
activation of LLM reasoning on high-information market events only". Rather than reasoning
on a fixed clock, the agent reasons when the market actually does something: a rolling
baseline of recent returns, and a z-score of the current move against it.

DELIBERATELY LOG-ONLY HERE. Enforcing it would cut the number of cycles on which all four
models are compared, and the whole competition contains about 27 remaining market hours —
too few to spend on suppressed observations. So the trigger is computed and recorded every
cycle, and `enforced` stays False. Turning it on later is a config change, and the log will
already show what it would have suppressed, which is the honest way to evaluate a gate
before trusting it.

The paper reports 157 autonomous invocations across 76 assets with an 11.5% agentic friction
rate as evidence the mechanism *operates* — explicitly not as evidence of profitability.
Same posture here: this measures event selection, not edge.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Z above which the latest move counts as a high-information event. 2.0 is roughly the 95th
# percentile of a normal baseline; returns are fat-tailed so the true rate is higher, which
# is the conservative direction for a trigger meant to catch real moves.
DEFAULT_Z_THRESHOLD = 2.0
BASELINE_WINDOW = 20  # trading days


@dataclass
class TriggerResult:
    z_score: Optional[float]
    latest_return: Optional[float]
    baseline_mean: Optional[float]
    baseline_std: Optional[float]
    samples: int
    triggered: bool
    enforced: bool = False   # log-only for now; see module docstring
    reason: str = ""

    def as_record(self) -> dict:
        return {
            "z_score": self.z_score,
            "latest_return": self.latest_return,
            "samples": self.samples,
            "triggered": self.triggered,
            "enforced": self.enforced,
            "reason": self.reason,
        }


def compute_trigger(
    stock_client: StockHistoricalDataClient,
    underlying: str,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    window: int = BASELINE_WINDOW,
) -> TriggerResult:
    """Z-score of the most recent daily return against a rolling baseline of the previous
    `window` returns. The current observation is excluded from its own baseline — the same
    mistake that pinned IV rank at 100, and it would bias every z-score toward zero here."""
    request = StockBarsRequest(
        symbol_or_symbols=underlying,
        timeframe=TimeFrame.Day,
        start=datetime.now() - timedelta(days=window * 3),  # buffer for weekends/holidays
    )
    bars = stock_client.get_stock_bars(request).df
    if bars.empty or len(bars) < window + 2:
        return TriggerResult(
            z_score=None, latest_return=None, baseline_mean=None, baseline_std=None,
            samples=len(bars), triggered=False,
            reason=f"insufficient history: {len(bars)} bars, need {window + 2}",
        )

    closes = bars["close"].tail(window + 2).tolist()
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

    latest = returns[-1]
    baseline = returns[:-1]  # excludes the observation being scored
    mean = statistics.fmean(baseline)
    std = statistics.pstdev(baseline)

    if std == 0:
        return TriggerResult(
            z_score=None, latest_return=round(latest, 6), baseline_mean=round(mean, 6),
            baseline_std=0.0, samples=len(baseline), triggered=False,
            reason="baseline has zero variance; z-score undefined",
        )

    z = (latest - mean) / std
    triggered = abs(z) >= z_threshold
    return TriggerResult(
        z_score=round(z, 3),
        latest_return=round(latest, 6),
        baseline_mean=round(mean, 6),
        baseline_std=round(std, 6),
        samples=len(baseline),
        triggered=triggered,
        reason=(
            f"|z|={abs(z):.2f} >= {z_threshold}: high-information event"
            if triggered
            else f"|z|={abs(z):.2f} < {z_threshold}: routine move"
        ),
    )
