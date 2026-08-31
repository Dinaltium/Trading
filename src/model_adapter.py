"""
One adapter function for every OpenAI-tool-calling-compatible provider (Groq, Featherless,
Mistral) — same request shape, just swap base_url + key. Claude Code CLI gets its own
wrapper below since it's a subprocess call, not an HTTP request.

Groq is the only provider whose output is EXECUTED (see risk_gate.py / execution.py).
Every other provider here is a SHADOW caller: its decision gets logged for the
Groq-vs-open-model comparison writeup, and never reaches order placement. See
BRAINSTORM.md section on the shadow-model architecture and AGENTS.md section 6b.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

from openai import OpenAI

# provider name -> (env var for key, base_url, default model)
PROVIDERS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    # Qwen3.5-9B, not Anubis-70B. Anubis is a roleplay/creative-writing finetune — it happens
    # to emit valid JSON, but "70B" is not the relevant axis when the tuning objective is
    # fiction. It also returns "temporarily at capacity" under load. Qwen3.5-9B measured
    # 4/4 clean parses at 3-8s with a stable pick, and is architecturally distinct from
    # Groq's gpt-oss-120b, which matters for a benchmark whose whole point is independence.
    "featherless": ("FEATHER_API_KEY", "https://api.featherless.ai/v1", "Qwen/Qwen3.5-9B"),
    # mistral-large-latest is gated behind a paid tier and returns 403 tier_not_allowed on
    # the free key; medium is the strongest model this account can actually call.
    "mistral": ("MISTRAL_API_KEY", "https://api.mistral.ai/v1", "mistral-medium-latest"),
    # Anthropic speaks the OpenAI chat-completions shape at this base_url, so Claude joins as
    # a plain HTTP provider rather than the `claude` subprocess. That subprocess could never
    # work unattended: the binary is absent from the GitHub Actions runner, so every CI cycle
    # logged "'claude' CLI not found on PATH" and ran three models while the writeup claimed
    # four. claude-sonnet-5 is a pinned snapshot, not an alias - from the 4.6 generation on,
    # the dateless ID maps to fixed weights. A benchmark whose point is comparing models is
    # worthless if one of them can silently change underneath it mid-competition.
    "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/", "claude-sonnet-5"),
}

# Providers whose failures are worth one immediate retry. Featherless returned "temporarily
# at capacity" once and unparseable output once in ten cycles; both are transient and both
# cost a shadow datapoint. Not applied blindly to every provider: a missing API key or a
# tier_not_allowed 403 will fail identically the second time and only wastes a cycle's time
# budget. See RETRYABLE_ERROR_MARKERS.
RETRYABLE_ERROR_MARKERS = (
    "temporarily at capacity",
    "no content in any response field",
    "rate limit",
    "429",
    "500",
    "502",
    "503",
    "504",
    "timeout",
)


# Anthropic rejects an identity-linked API key with 400 invalid_request_error unless the
# request names the workspace it acts in. A key issued under an organisation's workspace can
# be either kind and the error only appears at call time, so the header is sent when the id
# is configured and omitted when it is not - that way a plain workspace key needs no config
# and an identity-linked one needs one secret rather than a code change.
PROVIDER_HEADER_ENV = {
    "anthropic": ("anthropic-workspace-id", "ANTHROPIC_WORKSPACE_ID"),
}


def _extra_headers(provider: str) -> Optional[dict]:
    entry = PROVIDER_HEADER_ENV.get(provider)
    if not entry:
        return None
    header_name, env_var = entry
    value = os.getenv(env_var)
    return {header_name: value} if value else None


def _is_retryable(error: Optional[str]) -> bool:
    if not error:
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in RETRYABLE_ERROR_MARKERS)


def call_with_retry(provider: str, system_prompt: str, user_payload: dict, **kwargs) -> "ModelCallResult":
    """One retry for transient provider failures. Deliberately not a backoff loop - the
    scheduler gives each cycle a 90-second budget shared across four models, so a second
    attempt is affordable and a third is not."""
    result = call_openai_compatible(provider, system_prompt, user_payload, **kwargs)
    if result.ok or not _is_retryable(result.error):
        return result
    retried = call_openai_compatible(provider, system_prompt, user_payload, **kwargs)
    if not retried.ok:
        # Report both attempts so the audit log shows a retry happened and still failed,
        # rather than looking like a single unlucky call.
        retried.error = f"{retried.error} (retried once; first attempt: {result.error})"
    return retried


@dataclass
class ModelCallResult:
    provider: str
    ok: bool
    content: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[Any] = None


def call_openai_compatible(
    provider: str,
    system_prompt: str,
    user_payload: dict,
    model: Optional[str] = None,
    max_tokens: int = 600,
    temperature: float = 0.1,
) -> ModelCallResult:
    """Works for groq, featherless, mistral — anything speaking the OpenAI chat-completions
    shape. Returns a result object instead of raising, so a shadow-model outage never
    takes down the live Groq call or the loop around it."""
    if provider not in PROVIDERS:
        return ModelCallResult(provider, ok=False, error=f"unknown provider '{provider}'")

    env_var, base_url, default_model = PROVIDERS[provider]
    key = os.getenv(env_var)
    if not key:
        return ModelCallResult(provider, ok=False, error=f"{env_var} not set in environment")

    try:
        client = OpenAI(api_key=key, base_url=base_url, default_headers=_extra_headers(provider))
        resp = client.chat.completions.create(
            model=model or default_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, indent=2)},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        return ModelCallResult(provider, ok=False, error=str(e))

    if resp.choices is None:
        err = getattr(resp, "error", None)
        error_message = "empty response, no choices"
        if isinstance(err, dict):
            error_message = err.get("message") or str(err)
        elif err:
            error_message = str(err)
        return ModelCallResult(provider, ok=False, error=error_message)

    message = resp.choices[0].message
    content = message.content

    # Reasoning models return their answer in `reasoning` (or `reasoning_content`) and leave
    # `content` empty. Reading only `content` silently discarded the entire response and
    # reported "empty content field" — which looked like a provider outage but was ours.
    # It locked us out of every reasoning-capable model on Featherless, which is most of the
    # strong ones. Preference order matters: a model that fills BOTH puts its final answer
    # in content and its scratchpad in reasoning, so content wins whenever it is present.
    if not content:
        for attr in ("reasoning_content", "reasoning"):
            candidate = getattr(message, attr, None)
            if candidate:
                content = candidate
                break

    if not content:
        return ModelCallResult(provider, ok=False, error="no content in any response field", raw=resp)

    return ModelCallResult(provider, ok=True, content=content, raw=resp)


def call_claude_code_cli(
    system_prompt: str,
    user_payload: dict,
    timeout_seconds: int = 60,
) -> ModelCallResult:
    """Claude Code CLI headless mode — a subprocess call, not HTTP. Shadow-only:
    reuses the existing Claude Code subscription, no separate API billing.
    See BRAINSTORM.md section 5 for why this replaced 'switch to Claude mid-week'."""
    prompt = f"{system_prompt}\n\nInput:\n{json.dumps(user_payload, indent=2)}\n\nRespond with JSON only, no other text."
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",  # without this Windows decodes the CLI's stdout as cp1252 and
                               # mangles every non-ASCII character in the reasoning text
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return ModelCallResult("claude_code_cli", ok=False, error="'claude' CLI not found on PATH")
    except subprocess.TimeoutExpired:
        return ModelCallResult("claude_code_cli", ok=False, error=f"timed out after {timeout_seconds}s")

    if result.returncode != 0:
        return ModelCallResult("claude_code_cli", ok=False, error=result.stderr.strip()[:500])

    return ModelCallResult("claude_code_cli", ok=True, content=result.stdout.strip())


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=True)

    test_prompt = "You are a test responder. Reply with a JSON object: {\"word\": \"pong\"}"
    test_payload = {"ping": True}

    print("--- groq ---")
    print(call_openai_compatible("groq", test_prompt, test_payload))

    print("--- featherless ---")
    print(call_openai_compatible("featherless", test_prompt, test_payload))

    print("--- mistral (expected: no key yet) ---")
    print(call_openai_compatible("mistral", test_prompt, test_payload))
