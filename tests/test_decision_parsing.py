"""Covers the model-output parser. Every case here is a shape we have actually seen or
can plausibly get back from a provider — the point is that none of them may end up as a
silent {"ok": true, "decision": null, "error": null}."""

from src.decision_schema import parse_decision

VALID = """{"selected_strategy": "iron_condor", "confidence_score": 0.8,
            "reasoning": "high IV rank, neutral direction", "approved_for_execution": true}"""


def test_clean_json_parses():
    result = parse_decision(VALID)
    assert result.error is None
    assert result.decision["selected_strategy"] == "iron_condor"
    assert result.warnings == []


def test_fenced_json_parses():
    result = parse_decision(f"```json\n{VALID}\n```")
    assert result.error is None
    assert result.decision["confidence_score"] == 0.8


def test_prose_wrapped_json_parses():
    """The Claude Code CLI failure observed live: a correct decision buried in commentary."""
    result = parse_decision(f"Here is my analysis.\n\n{VALID}\n\nLet me know if you need more.")
    assert result.error is None
    assert result.decision["selected_strategy"] == "iron_condor"


def test_brace_inside_reasoning_does_not_truncate():
    text = """{"selected_strategy": "cash", "confidence_score": 0.5,
               "reasoning": "regime flag {set} and unbalanced }", "approved_for_execution": false}"""
    result = parse_decision(text)
    assert result.error is None
    assert result.decision["reasoning"] == "regime flag {set} and unbalanced }"


def test_unparseable_output_reports_error_and_keeps_raw():
    result = parse_decision("I cannot produce JSON right now.")
    assert result.decision is None
    assert result.error == "no JSON object found in model output"
    assert result.raw == "I cannot produce JSON right now."


def test_malformed_json_reports_decode_error():
    result = parse_decision('{"selected_strategy": "cash", ')
    assert result.decision is None
    assert "JSON decode failed" in result.error


def test_missing_field_is_fatal():
    result = parse_decision('{"selected_strategy": "cash", "confidence_score": 0.5}')
    assert result.decision is None
    assert "missing required field" in result.error


def test_unknown_strategy_is_fatal():
    text = """{"selected_strategy": "naked_call", "confidence_score": 0.9,
               "reasoning": "x", "approved_for_execution": true}"""
    result = parse_decision(text)
    assert result.decision is None
    assert "not one of" in result.error


def test_cash_with_approved_true_is_normalised():
    """Observed from Featherless: contradictory, non-fatal, must be recorded not hidden."""
    text = """{"selected_strategy": "cash", "confidence_score": 0.9,
               "reasoning": "high vol", "approved_for_execution": true}"""
    result = parse_decision(text)
    assert result.decision["approved_for_execution"] is False
    assert any("normalised to false" in w for w in result.warnings)


def test_out_of_range_confidence_is_clamped():
    text = """{"selected_strategy": "cash", "confidence_score": 1.4,
               "reasoning": "x", "approved_for_execution": false}"""
    result = parse_decision(text)
    assert result.decision["confidence_score"] == 1.0
    assert any("clamped" in w for w in result.warnings)


def test_empty_and_none_content():
    assert parse_decision(None).error == "no content returned by provider"
    assert parse_decision("   ").error == "provider returned empty output"
