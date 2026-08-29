"""
Non-secret, remotely-toggleable settings — which provider executes live trades,
which underlyings are in scope, and a global pause switch. Set via the password-
protected /admin dashboard, written to config/live_settings.json and pushed to
GitHub from there; pulled fresh here at the start of every scheduler tick.

Deliberately NOT here: anything in risk_limits.yaml (max loss %, drawdown halt,
Kelly fraction). Those stay git-committed, hand-edited only — remotely toggling
risk limits, even behind a password, would undermine the "risk gate is hard-coded,
never tamperable" property the whole architecture is built on. See BRAINSTORM.md.

Fails safe: any fetch/parse error, or a provider not in ALLOWED_LIVE_PROVIDERS,
falls back to the hard-coded default (Groq live, SPY+QQQ, not paused) rather than
either crashing the scheduler or silently trusting malformed remote input.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

import requests

RAW_URL = "https://raw.githubusercontent.com/Dinaltium/Trading/main/config/live_settings.json"
ALLOWED_LIVE_PROVIDERS = {"groq", "featherless", "mistral"}  # claude_code_cli stays shadow-only, see module docstring
FETCH_TIMEOUT_SECONDS = 10


@dataclass
class LiveSettings:
    active_model_provider: str = "groq"
    underlyings: list[str] = field(default_factory=lambda: ["SPY", "QQQ"])
    trading_paused: bool = False


DEFAULT_SETTINGS = LiveSettings()


def fetch_live_settings() -> LiveSettings:
    try:
        resp = requests.get(RAW_URL, timeout=FETCH_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            print(f"[live_settings] fetch returned {resp.status_code}, using defaults")
            return DEFAULT_SETTINGS
        data = resp.json()
    except Exception as e:
        print(f"[live_settings] fetch/parse failed ({e}), using defaults")
        return DEFAULT_SETTINGS

    provider = data.get("active_model_provider", "groq")
    if provider not in ALLOWED_LIVE_PROVIDERS:
        print(f"[live_settings] '{provider}' not an allowed live provider, falling back to groq")
        provider = "groq"

    underlyings = data.get("underlyings")
    if not isinstance(underlyings, list) or not underlyings:
        underlyings = DEFAULT_SETTINGS.underlyings

    trading_paused = bool(data.get("trading_paused", False))

    return LiveSettings(
        active_model_provider=provider,
        underlyings=[str(u).upper() for u in underlyings],
        trading_paused=trading_paused,
    )


if __name__ == "__main__":
    print(fetch_live_settings())
