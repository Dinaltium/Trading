"""
Integrity-guard behaviour. Cases are drawn from failures actually observed in
logs/archive/audit_log_dev-and-test_through_2026-08-30.jsonl wherever possible, so the
suite documents real faults rather than imagined ones.
"""

import pytest

from src.guards import (
    ExecutionBreaker,
    check_faithfulness,
    cross_model_agreement,
    reconcile_positions,
    validate_signals,
)

GOOD_SIGNALS = {
    "underlying": "SPY",
    "current_price": 769.35,
    "classifier_p_up": 0.4069,
    "iv_rank": 86.69,
    "iv_percentile": 55.56,
    "iv_history_samples": 63,
    "vrp": -0.0148,
    "market_regime": "HIGH_VOLATILITY",
}


# --- input sanitization -------------------------------------------------------

def test_clean_signals_pass():
    result = validate_signals(GOOD_SIGNALS)
    assert result.passed
    assert result.failures == []


def test_probability_out_of_range_fails():
    result = validate_signals({**GOOD_SIGNALS, "classifier_p_up": 1.4})
    assert not result.passed
    assert any("classifier_p_up" in f for f in result.failures)


def test_nan_signal_fails():
    result = validate_signals({**GOOD_SIGNALS, "vrp": float("nan")})
    assert not result.passed


def test_non_numeric_signal_fails():
    result = validate_signals({**GOOD_SIGNALS, "iv_rank": "high"})
    assert not result.passed
    assert any("expected a number" in f for f in result.failures)


def test_absent_signal_is_not_a_failure():
    """iv_rank is legitimately None before enough history accumulates."""
    signals = {**GOOD_SIGNALS, "iv_rank": None, "iv_percentile": None}
    assert validate_signals(signals).passed


def test_saturated_rank_warns_but_does_not_block():
    """The exact signature of the degenerate-window bug: legal value, broken meaning."""
    result = validate_signals({**GOOD_SIGNALS, "iv_rank": 100.0, "iv_percentile": 100.0})
    assert result.passed
    assert any("degenerate" in w for w in result.warnings)


def test_rank_percentile_divergence_warns():
    result = validate_signals({**GOOD_SIGNALS, "iv_rank": 100.0, "iv_percentile": 20.0})
    assert result.passed
    assert any("disagree" in w for w in result.warnings)


def test_thin_history_warns():
    result = validate_signals({**GOOD_SIGNALS, "iv_history_samples": 14})
    assert any("14 samples" in w for w in result.warnings)


# --- faithfulness -------------------------------------------------------------

def test_accurate_reasoning_passes():
    """Real Groq output from 2026-08-30, quoting its inputs correctly."""
    reasoning = (
        "P(Up)=0.4069 indicates bearish bias; IV rank 86.69 provides rich premium; "
        "market regime HIGH_VOLATILITY supports defined-risk bear put spread."
    )
    assert check_faithfulness(reasoning, GOOD_SIGNALS).passed


def test_rounded_citation_passes():
    """'IV rank 86.7' about 86.69 is accurate prose, not fabrication."""
    assert check_faithfulness("IV rank 86.7 is elevated", GOOD_SIGNALS).passed


def test_fabricated_value_fails():
    result = check_faithfulness("IV rank 42.0 is low, so we buy premium", GOOD_SIGNALS)
    assert not result.passed
    assert any("42.0" in f and "86.69" in f for f in result.failures)


def test_fabricated_probability_fails():
    result = check_faithfulness("P(Up)=0.72 is strongly bullish", GOOD_SIGNALS)
    assert not result.passed


def test_repeated_wrong_figure_is_one_failure():
    result = check_faithfulness(
        "IV rank 42.0 is low. Because IV rank 42.0 is low, we act.", GOOD_SIGNALS
    )
    assert len(result.failures) == 1


def test_reasoning_without_numbers_passes_with_warning():
    result = check_faithfulness("Conditions look unfavourable, staying in cash.", GOOD_SIGNALS)
    assert result.passed
    assert any("quoted no signal values" in w for w in result.warnings)


def test_unrelated_numbers_are_not_flagged():
    """Strike prices and contract counts are not signal claims."""
    reasoning = "Sell the 760/755 put spread, 10 contracts, 30 days out."
    assert check_faithfulness(reasoning, GOOD_SIGNALS).passed


def test_missing_reasoning_passes():
    assert check_faithfulness(None, GOOD_SIGNALS).passed


# --- cross-model agreement ----------------------------------------------------

def shadow(strategy):
    return {"ok": True, "decision": {"selected_strategy": strategy}}


def test_unanimous_agreement():
    shadows = {"featherless": shadow("cash"), "mistral": shadow("cash"), "claude_code_cli": shadow("cash")}
    result = cross_model_agreement("cash", shadows)
    assert result["unanimous"]
    assert result["shadows_agreeing"] == 3
    assert not result["live_is_lone_dissenter"]


def test_lone_dissenting_live_model_is_flagged():
    shadows = {"featherless": shadow("cash"), "mistral": shadow("cash")}
    result = cross_model_agreement("iron_condor", shadows)
    assert result["live_is_lone_dissenter"]
    assert result["shadows_agreeing"] == 0


def test_failed_shadows_are_excluded_not_counted_as_disagreement():
    shadows = {
        "featherless": shadow("cash"),
        "mistral": {"ok": False, "decision": None, "error": "403"},
    }
    result = cross_model_agreement("cash", shadows)
    assert result["shadows_responding"] == 1
    assert result["unanimous"]


# --- reconciliation -----------------------------------------------------------

def test_matching_state_reconciles():
    broker = {"ok": True, "underlyings": ["SPY"], "equity": 100_007.79}
    assert reconcile_positions({"SPY"}, 100_007.79, broker).passed


def test_unknown_broker_position_fails():
    """The dangerous direction: the broker holds risk the agent is not counting."""
    broker = {"ok": True, "underlyings": ["SPY", "QQQ"], "equity": 100_007.79}
    result = reconcile_positions({"SPY"}, 100_007.79, broker)
    assert not result.passed
    assert any("QQQ" in f for f in result.failures)


def test_phantom_position_warns_only():
    """Agent over-counting its own risk is conservative, so it warns rather than blocks."""
    broker = {"ok": True, "underlyings": [], "equity": 100_007.79}
    result = reconcile_positions({"SPY"}, 100_007.79, broker)
    assert result.passed
    assert any("SPY" in w for w in result.warnings)


def test_equity_drift_fails():
    broker = {"ok": True, "underlyings": [], "equity": 90_000.0}
    result = reconcile_positions(set(), 100_000.0, broker)
    assert not result.passed
    assert any("equity mismatch" in f for f in result.failures)


def test_unreadable_broker_state_fails_closed():
    result = reconcile_positions({"SPY"}, 100_000.0, {"ok": False, "error": "timeout"})
    assert not result.passed


# --- circuit breaker ----------------------------------------------------------

def test_breaker_trips_after_threshold():
    breaker = ExecutionBreaker(max_consecutive_failures=3)
    for _ in range(2):
        breaker.record_failure("connection reset")
    assert breaker.check().passed
    breaker.record_failure("connection reset")
    assert not breaker.check().passed


def test_success_resets_the_counter():
    breaker = ExecutionBreaker(max_consecutive_failures=3)
    breaker.record_failure("x")
    breaker.record_failure("x")
    breaker.record_success()
    breaker.record_failure("x")
    assert breaker.check().passed


def test_tripped_breaker_stays_tripped_until_reset():
    breaker = ExecutionBreaker(max_consecutive_failures=1)
    breaker.record_failure("x")
    breaker.record_success()
    assert not breaker.check().passed, "a success must not silently clear a tripped breaker"
    breaker.reset()
    assert breaker.check().passed
