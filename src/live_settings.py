"""
Non-secret, remotely-toggleable settings — which provider executes live trades,
which underlyings are in scope, and a global pause switch. Set via the password-
protected /admin dashboard, written to config/live_settings.json and pushed to
GitHub from there; pulled fresh here at the start of every scheduler tick.

Deliberately NOT here: anything in risk_limits.yaml (max loss %, drawdown halt,
Kelly fraction). Those stay git-committed, hand-edited only — remotely toggling
risk limits, even behind a password, would undermine the "risk gate is hard-coded,
never tamperable" property the whole architecture is built on. See BRAINSTORM.md.

All four models can now be selected as the live one. Whichever is chosen executes;
the other three automatically fall to shadow. See ALLOWED_LIVE_PROVIDERS for the
claude_code_cli caveat.

Fails safe: any fetch/parse error, or a provider not in ALLOWED_LIVE_PROVIDERS,
falls back to the hard-coded default (Groq live, SPY+QQQ, not paused) rather than
either crashing the scheduler or silently trusting malformed remote input.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

import requests

RAW_URL = "https://raw.githubusercontent.com/Dinaltium/Trading/main/config/live_settings.json"
ALLOWED_LIVE_PROVIDERS = {"groq", "featherless", "mistral", "claude_code_cli"}
# claude_code_cli is selectable but carries a real caveat: it shells out to the `claude`
# binary, which exists on a developer laptop and NOT on the GitHub Actions runner. Selected
# there, every cycle returns "'claude' CLI not found on PATH", no decision is produced and
# nothing trades. The /admin UI says so at the point of choosing.
FETCH_TIMEOUT_SECONDS = 10


# Three states, not two. "paused" refuses everything, which is the wrong tool when
# positions are already open — it stops the agent taking risk and simultaneously stops it
# managing the risk it took. "exit_only" refuses new entries while still running stop-loss
# evaluation and closing orders. That distinction only became meaningful once the agent
# gained the ability to close a position at all; see src/positions.py.
TRADING_MODES = ("running", "exit_only", "paused")


@dataclass
class LiveSettings:
    active_model_provider: str = "groq"
    underlyings: list[str] = field(default_factory=lambda: ["SPY", "QQQ"])
    trading_mode: str = "running"

    @property
    def may_open_new_positions(self) -> bool:
        return self.trading_mode == "running"

    @property
    def may_close_positions(self) -> bool:
        return self.trading_mode in ("running", "exit_only")

    @property
    def trading_paused(self) -> bool:
        """Retained so older callers and the dashboard keep working."""
        return self.trading_mode == "paused"


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

    # Accept the newer trading_mode, falling back to the older boolean so a settings file
    # written before this change still resolves to a valid state rather than a crash.
    mode = data.get("trading_mode")
    if mode not in TRADING_MODES:
        if mode is not None:
            print(f"[live_settings] '{mode}' is not a valid trading mode, falling back")
        mode = "paused" if bool(data.get("trading_paused", False)) else "running"

    return LiveSettings(
        active_model_provider=provider,
        underlyings=[str(u).upper() for u in underlyings],
        trading_mode=mode,
    )


if __name__ == "__main__":
    print(fetch_live_settings())
