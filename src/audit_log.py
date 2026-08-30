"""
One structured JSON-lines record per trading cycle: signals used, the live Groq decision,
every shadow model's pick, the risk gate's verdict, and the fill result if any. This is
the single source both the one-pager and the model-benchmark writeup draw from — per the
blueprint (BRAINSTORM.md section 9), never reconstructed from memory after the fact.
"""

import json
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "audit_log.jsonl"
REPO_ROOT = LOG_PATH.parent.parent


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]
    if hasattr(obj, "value"):  # enums (OrderSide, PositionIntent, etc.)
        return obj.value
    return obj


def write_cycle_record(
    underlying: str,
    signals: dict,
    live_decision: Optional[dict],
    shadow_decisions: dict,
    risk_gate_verdict: Optional[dict],
    fill_result: Optional[dict],
    dry_run: bool,
    account_equity: Optional[float] = None,
    live_provider: str = "groq",
    live_decision_error: Optional[str] = None,
    live_decision_warnings: Optional[list] = None,
    live_rulebook: Optional[dict] = None,
    guards: Optional[dict] = None,
    log_path: Path = LOG_PATH,
) -> dict:
    log_path.parent.mkdir(exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "underlying": underlying,
        "dry_run": dry_run,
        "account_equity": account_equity,
        "signals": _to_jsonable(signals),
        "live_decision": {"provider": live_provider, **_to_jsonable(live_decision)} if live_decision else None,
        # Set only when the live provider produced no usable decision. Distinguishes a
        # failed/unparseable call from a genuine "cash" pick, which otherwise look
        # identical downstream (both leave live_decision falsy and skip the risk gate).
        "live_decision_error": live_decision_error,
        "live_decision_warnings": live_decision_warnings or None,
        # Whether the live model agreed with the deterministic rulebook, abstained from
        # it, or went off-book. The model-comparison writeup is built from this field.
        "live_rulebook": live_rulebook,
        # Integrity-guard verdicts, one per TradeTrap component. See src/guards.py.
        "guards": _to_jsonable(guards) if guards else None,
        "shadow_decisions": _to_jsonable(shadow_decisions),
        "risk_gate_verdict": _to_jsonable(risk_gate_verdict),
        "fill_result": _to_jsonable(fill_result),
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def write_exit_record(
    exit_result: dict,
    dry_run: bool,
    log_path: Path = LOG_PATH,
) -> Optional[dict]:
    """Append one record for an exit pass that actually did something.

    The exit path used to be invisible: close_spread_via_cli built a dict its own docstring
    called audit-ready, manage_open_positions returned it, and the scheduler print()ed it to
    stdout and dropped it. Nothing about closing a position ever reached the audit log, so a
    stop-loss that fired left no durable trace while every entry decision did.

    Returns None when nothing happened, so a quiet tick does not pad the log. Holds are
    summarised rather than written in full — the interesting event is the close."""
    if not exit_result or not exit_result.get("ok"):
        if exit_result and exit_result.get("error"):
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "record_type": "exit_pass",
                "dry_run": dry_run,
                "error": exit_result.get("error"),
            }
        else:
            return None
    else:
        closed = exit_result.get("closed") or []
        held = exit_result.get("held") or []
        if not closed:
            return None  # nothing closed: the held summary lives in the cycle records already
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "record_type": "exit_pass",
            "dry_run": dry_run,
            "open_spreads": exit_result.get("open_spreads"),
            "closed": _to_jsonable(closed),
            "held_count": len(held),
        }

    log_path.parent.mkdir(exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def push_audit_log(commit_message: Optional[str] = None) -> bool:
    """Best-effort git add+commit+push of the audit log so the deployed dashboard
    (which has no access to this machine's filesystem — see dashboard/) can read
    fresh cycle data from GitHub. Called once per scheduler tick (not per write —
    see scheduler.py), never during weekend soak/test-mode runs to avoid spamming
    the repo with test commits. Failures are logged and swallowed, never raised —
    a git/network hiccup must not take down the trading loop."""
    message = commit_message or f"audit log: cycle at {datetime.now(timezone.utc).isoformat()}"
    try:
        # The whole of logs/, not just the audit log — .gitignore already narrows this to
        # the four things that must survive: the audit log, the IV history window, agent
        # state, and the archived evidence. The next cycle runs on a fresh CI runner holding
        # only what is committed here, so unpushed state is state the agent will not have.
        subprocess.run(["git", "add", "--", "logs/"], cwd=REPO_ROOT, check=True, capture_output=True, text=True)
        commit = subprocess.run(["git", "commit", "-m", message], cwd=REPO_ROOT, capture_output=True, text=True)
        if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
            print(f"[audit_log push] commit failed: {commit.stderr.strip()}")
            return False
        if "nothing to commit" in commit.stdout:
            return True  # no new records since last push — not an error
        push = subprocess.run(["git", "push"], cwd=REPO_ROOT, capture_output=True, text=True)
        if push.returncode != 0:
            print(f"[audit_log push] push failed: {push.stderr.strip()}")
            return False
        return True
    except Exception as e:
        print(f"[audit_log push] unexpected error: {e}")
        return False


if __name__ == "__main__":
    rec = write_cycle_record(
        underlying="SPY",
        signals={"classifier_p_up": 0.5, "iv_rank": None},
        live_decision={"selected_strategy": "cash", "confidence_score": 0.5, "reasoning": "test", "approved_for_execution": False},
        shadow_decisions={"claude_code_cli": {"ok": False, "error": "not tested yet"}},
        risk_gate_verdict=None,
        fill_result=None,
        dry_run=True,
    )
    print(json.dumps(rec, indent=2))
