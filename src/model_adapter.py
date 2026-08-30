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
}


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
        client = OpenAI(api_key=key, base_url=base_url)
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
