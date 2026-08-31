"""Retry policy and provider registry.

The retry exists because Featherless failed twice in ten cycles - once "temporarily at
capacity", once with unparseable output - and each failure cost a shadow datapoint from a
benchmark that only has a few days to collect any.
"""

import src.model_adapter as ma


def test_anthropic_is_registered_as_an_http_provider():
    env_var, base_url, model = ma.PROVIDERS["anthropic"]
    assert env_var == "ANTHROPIC_API_KEY"
    assert base_url == "https://api.anthropic.com/v1/"
    assert model == "claude-sonnet-5"


def test_transient_failures_are_retryable():
    assert ma._is_retryable("TheDrummer/Anubis-70B-v1 is temporarily at capacity")
    assert ma._is_retryable("no content in any response field")
    assert ma._is_retryable("429 rate limit exceeded")
    assert ma._is_retryable("upstream 503")


def test_permanent_failures_are_not_retried():
    """A missing key or a tier refusal fails identically the second time. Retrying only
    burns the cycle's shared 90-second budget."""
    assert not ma._is_retryable("MISTRAL_API_KEY not set in environment")
    assert not ma._is_retryable("403 tier_not_allowed")
    assert not ma._is_retryable(None)
    assert not ma._is_retryable("")


def test_retry_is_attempted_once_then_reports_both_attempts(monkeypatch):
    calls = []

    def fake(provider, system_prompt, user_payload, **kwargs):
        calls.append(provider)
        return ma.ModelCallResult(provider, ok=False, error="temporarily at capacity")

    monkeypatch.setattr(ma, "call_openai_compatible", fake)
    result = ma.call_with_retry("featherless", "sys", {})
    assert len(calls) == 2, "transient failure should be retried exactly once"
    assert not result.ok
    assert "retried once" in result.error


def test_success_on_retry_is_reported_clean(monkeypatch):
    seq = [
        ma.ModelCallResult("featherless", ok=False, error="temporarily at capacity"),
        ma.ModelCallResult("featherless", ok=True, content='{"selected_strategy": "cash"}'),
    ]

    def fake(provider, system_prompt, user_payload, **kwargs):
        return seq.pop(0)

    monkeypatch.setattr(ma, "call_openai_compatible", fake)
    result = ma.call_with_retry("featherless", "sys", {})
    assert result.ok
    assert result.error is None


def test_permanent_failure_is_not_retried(monkeypatch):
    calls = []

    def fake(provider, system_prompt, user_payload, **kwargs):
        calls.append(provider)
        return ma.ModelCallResult(provider, ok=False, error="ANTHROPIC_API_KEY not set in environment")

    monkeypatch.setattr(ma, "call_openai_compatible", fake)
    ma.call_with_retry("anthropic", "sys", {})
    assert len(calls) == 1


def test_claude_cli_is_out_of_the_cycle_provider_set():
    """It cannot run on the CI runner, so counting it produced four names and three answers."""
    from src.orchestrator import ALL_PROVIDERS, CLAUDE_CLI_PROVIDER

    assert CLAUDE_CLI_PROVIDER not in ALL_PROVIDERS
    assert ALL_PROVIDERS == ["groq", "featherless", "mistral", "anthropic"]


def test_workspace_header_sent_only_when_configured(monkeypatch):
    """An identity-linked Anthropic key 400s without the workspace id; a plain workspace key
    needs no header at all. Sending it conditionally covers both without a code change."""
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    assert ma._extra_headers("anthropic") is None
    assert ma._extra_headers("groq") is None

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test")
    assert ma._extra_headers("anthropic") == {"anthropic-workspace-id": "wrkspc_test"}
    assert ma._extra_headers("groq") is None
