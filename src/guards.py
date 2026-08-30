"""
Integrity guards — the "antivirus" layer.

Structured after TradeTrap (arXiv:2512.02261, Yan et al., Shanghai AI Laboratory), which
decomposes an LLM trading agent into four attack surfaces and names a mitigation for each.
Their central finding is the one that matters here: a small perturbation at ONE component
propagates through the decision loop and produces extreme concentration, runaway exposure
and large drawdowns. So the defences have to sit at each boundary, not only at the end.

  TradeTrap component      Their mitigation          Implemented here
  ---------------------    ----------------------    ----------------------------------
  Market intelligence      input sanitization        validate_signals()
                           cross-validation          cross_model_agreement()
  Strategy formulation     input guardrails          decision_schema.rulebook (existing)
                           (fabrication detection)   check_faithfulness()
  Portfolio & ledger       reconciliation            reconcile_positions()
  Trade execution          circuit breaker           ExecutionBreaker
                           minimal permissions       alpaca_cli.verify_paper_endpoint()

Everything here is deterministic. No guard calls a model — a guard that asked an LLM
whether the LLM was lying would defeat its own purpose.
"""

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

# --- shared result type -------------------------------------------------------


@dataclass
class GuardResult:
    """passed=False means the cycle must not proceed to execution. warnings never block;
    they are recorded so a slow degradation is visible in the log before it becomes a loss."""
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_record(self) -> dict:
        return {
            "passed": self.passed,
            "failures": self.failures or None,
            "warnings": self.warnings or None,
        }


# --- 1. market intelligence: input sanitization -------------------------------

# Ranges the signal vector must satisfy before any model sees it. These are definitional,
# not tuning knobs: a probability outside [0,1] or a rank outside [0,100] means the signal
# pipeline is broken, and a model asked to reason about it will confabulate a justification
# rather than object.
SIGNAL_BOUNDS = {
    "classifier_p_up": (0.0, 1.0),
    "iv_rank": (0.0, 100.0),
    "iv_percentile": (0.0, 100.0),
    "current_price": (0.01, 100_000.0),
    "vrp": (-5.0, 5.0),
}

MAX_PRICE_STALENESS = timedelta(days=5)  # generous: covers a long holiday weekend


def validate_signals(signals: dict, now: Optional[datetime] = None) -> GuardResult:
    """Reject a malformed or fabricated signal vector before it reaches any model.

    This is the guard the IV-rank bug would have caught. When iv_rank was pinned at exactly
    100.0 for 23% of cycles, nothing objected — the value was in range, so only the
    consistency check below flags it as suspicious rather than impossible."""
    failures: list[str] = []
    warnings: list[str] = []

    for key, (lo, hi) in SIGNAL_BOUNDS.items():
        value = signals.get(key)
        if value is None:
            continue  # legitimately absent (e.g. iv_rank before enough history) - not a failure
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"{key} is {type(value).__name__}, expected a number")
            continue
        if math.isnan(value) or math.isinf(value):
            failures.append(f"{key} is {value}")
            continue
        if not lo <= value <= hi:
            failures.append(f"{key}={value} outside valid range [{lo}, {hi}]")

    # Internal consistency. Rank and percentile measure the same underlying quantity against
    # the same window, so they cannot disagree wildly; when they do, one of them is wrong.
    rank, pct = signals.get("iv_rank"), signals.get("iv_percentile")
    if isinstance(rank, (int, float)) and isinstance(pct, (int, float)):
        if abs(rank - pct) > 60:
            warnings.append(
                f"iv_rank ({rank}) and iv_percentile ({pct}) disagree by more than 60 points; "
                "one of the two is likely computed from a corrupted window"
            )

    # A rank of exactly 0 or exactly 100 is legal but is also the signature of a degenerate
    # window - it is what a min-max rank returns when the current sample IS the extreme.
    if isinstance(rank, (int, float)) and rank in (0.0, 100.0):
        warnings.append(f"iv_rank is exactly {rank} — check the ranking window is not degenerate")

    samples = signals.get("iv_history_samples")
    if isinstance(samples, int) and 0 < samples < 20:
        warnings.append(f"iv_rank backed by only {samples} samples; treat as low-confidence")

    return GuardResult(passed=not failures, failures=failures, warnings=warnings)


# --- 2. strategy formulation: faithfulness ------------------------------------

# TradeTrap's data-fabrication surface, applied to the model's own output. A model that
# cites a number it was never given has either hallucinated its input or is reasoning about
# a different cycle; either way its conclusion is unsupported even when it happens to be
# the correct strategy.

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

# Phrases that introduce a signal, mapped to the payload key they refer to. Matching is
# deliberately narrow: a claim is only checked when the model names the signal explicitly.
_SIGNAL_PHRASES = {
    "classifier_p_up": [r"p\s*\(\s*up\s*\)", r"p_up", r"probability of up", r"classifier"],
    "iv_rank": [r"iv[\s_-]*rank"],
    "iv_percentile": [r"iv[\s_-]*percentile"],
    "vrp": [r"\bvrp\b", r"volatility risk premium"],
}

FAITHFULNESS_TOLERANCE = 0.02  # relative; covers legitimate rounding in prose


def check_faithfulness(reasoning: Optional[str], signals: dict) -> GuardResult:
    """Verify that every signal value the model quotes matches what it was handed.

    Only claims where the model names the signal are checked, and a number is accepted if
    it matches at any plausible rounding. The check is designed to produce zero false
    positives on honest prose and to fire hard on a fabricated figure."""
    if not reasoning:
        return GuardResult(passed=True, warnings=["no reasoning text to verify"])

    text = reasoning.lower()
    failures: list[str] = []
    checked = 0

    for key, patterns in _SIGNAL_PHRASES.items():
        actual = signals.get(key)
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            continue

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                # Look at the text just after the signal name for the number it claims.
                window = text[match.end() : match.end() + 40]
                numbers = _NUMBER_RE.findall(window)
                if not numbers:
                    continue
                claimed = float(numbers[0])
                checked += 1
                if not _matches_at_some_rounding(claimed, actual):
                    failures.append(
                        f"reasoning cites {key}={claimed} but the model was given {actual}"
                    )
                break  # one claim per pattern is enough

    if failures:
        # Deduplicate: a model repeating the same wrong figure is one fault, not three.
        failures = sorted(set(failures))
        return GuardResult(passed=False, failures=failures)

    return GuardResult(
        passed=True,
        warnings=[] if checked else ["reasoning quoted no signal values; nothing to verify"],
    )


def _matches_at_some_rounding(claimed: float, actual: float) -> bool:
    """A model writing 'IV rank 86.7' about 86.69 is being accurate, not fabricating.
    Accept the claim if it equals the true value rounded to any sensible precision, or
    falls inside a small relative tolerance."""
    for places in (0, 1, 2, 3, 4):
        if abs(claimed - round(actual, places)) < 1e-9:
            return True
    if actual != 0 and abs(claimed - actual) / abs(actual) <= FAITHFULNESS_TOLERANCE:
        return True
    return abs(claimed - actual) < 1e-9


# --- 3. market intelligence: cross-validation ---------------------------------


def cross_model_agreement(live_strategy: Optional[str], shadow_decisions: dict) -> dict:
    """How many independent models, given identical signals, reached the live model's answer.

    This is TradeTrap's cross-validation mitigation, which we already satisfy structurally by
    running four models per cycle. Unanimity is not proof of correctness — all four share a
    rulebook and can be wrong together — but a lone dissenting live model is worth seeing in
    the log, because a compromised or drifting primary shows up here first."""
    picks = {}
    for provider, entry in (shadow_decisions or {}).items():
        decision = (entry or {}).get("decision")
        if decision:
            picks[provider] = decision.get("selected_strategy")

    agreeing = [p for p, s in picks.items() if s == live_strategy]
    responded = len(picks)
    return {
        "live_strategy": live_strategy,
        "shadow_picks": picks,
        "shadows_responding": responded,
        "shadows_agreeing": len(agreeing),
        "unanimous": responded > 0 and len(agreeing) == responded,
        "live_is_lone_dissenter": responded >= 2 and len(agreeing) == 0,
    }


# --- 4. portfolio & ledger: reconciliation ------------------------------------


def reconcile_positions(believed_underlyings: set, believed_equity: float, broker_state: dict) -> GuardResult:
    """Compare what the agent thinks it holds against what the broker actually reports.

    TradeTrap's memory-poisoning and state-tampering surface. It is also the mundane failure:
    a fill that arrived after our snapshot, a manually closed leg, a crashed cycle. Trading on
    a stale position map is how a diversification cap silently stops capping."""
    failures: list[str] = []
    warnings: list[str] = []

    if not broker_state.get("ok"):
        # Cannot verify - refuse rather than assume. A reconciliation that fails open is not
        # a reconciliation.
        return GuardResult(
            passed=False,
            failures=[f"could not read broker state for reconciliation: {broker_state.get('error')}"],
        )

    actual_underlyings = set(broker_state.get("underlyings") or [])
    missing = actual_underlyings - believed_underlyings
    phantom = believed_underlyings - actual_underlyings

    if missing:
        failures.append(f"broker holds positions the agent does not know about: {sorted(missing)}")
    if phantom:
        warnings.append(f"agent believes it holds positions the broker does not report: {sorted(phantom)}")

    actual_equity = broker_state.get("equity")
    if isinstance(actual_equity, (int, float)) and believed_equity:
        drift = abs(actual_equity - believed_equity) / abs(believed_equity)
        if drift > 0.01:
            failures.append(
                f"equity mismatch: agent believes ${believed_equity:,.2f}, "
                f"broker reports ${actual_equity:,.2f} ({drift:.2%} drift)"
            )

    return GuardResult(passed=not failures, failures=failures, warnings=warnings)


# --- 5. execution: circuit breaker --------------------------------------------


@dataclass
class ExecutionBreaker:
    """Trips after consecutive execution failures and stays tripped until reset.

    TradeTrap's execution surface covers latency flooding and tool misuse, where the
    characteristic damage is a retry loop hammering the broker. The drawdown halt already
    bounds losses from bad trades; this bounds damage from a broken execution path, which is
    a different failure with a different signature."""
    max_consecutive_failures: int = 3
    consecutive_failures: int = 0
    tripped: bool = False
    last_error: Optional[str] = None
    failures_at_trip: int = 0  # frozen at trip time; the live counter keeps moving afterwards

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.last_error = None

    def record_failure(self, error: str) -> None:
        self.consecutive_failures += 1
        self.last_error = error
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.tripped = True
            self.failures_at_trip = self.consecutive_failures

    def check(self) -> GuardResult:
        if self.tripped:
            return GuardResult(
                passed=False,
                failures=[
                    f"execution circuit breaker tripped after {self.failures_at_trip} "
                    f"consecutive failures; last error: {self.last_error}"
                ],
            )
        return GuardResult(passed=True)

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.tripped = False
        self.last_error = None
        self.failures_at_trip = 0


# --- aggregate -----------------------------------------------------------------


def run_pre_decision_guards(signals: dict) -> GuardResult:
    """Everything that must hold before a model is asked anything at all."""
    return validate_signals(signals)


def run_post_decision_guards(decision: Optional[dict], signals: dict) -> GuardResult:
    """Everything that must hold before a model's answer is allowed near the risk gate."""
    if not decision:
        return GuardResult(passed=True, warnings=["no decision to verify"])
    return check_faithfulness(decision.get("reasoning"), signals)
