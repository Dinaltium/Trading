"""
Order submission through Alpaca's official CLI (`alpaca`), not the Python SDK.

Two reasons this exists, and only the second is about the hackathon's requirements.

1. It is a real safety property. `alpaca doctor` resolves the trading endpoint through
   the CLI's own precedence chain (ALPACA_LIVE_TRADE, then the profile's live_trade
   field, then a paper default) and prints the answer. We require that printed line to
   read paper-api before any order is built. The check runs out-of-process, in a binary
   we did not write, against the same profile the order will use — so it cannot be
   satisfied by a mistake in our own config parsing. An exported ALPACA_LIVE_TRADE=true
   would send a profile literally named "paper" to the live endpoint; this catches that,
   and nothing in the SDK path ever could.

2. The hackathon requires projects to use Alpaca's MCP server or CLI. We use the CLI,
   for the execution path specifically — the point at which being wrong costs money.

Deliberately NOT using -p/--profile anywhere. `alpaca doctor` accepts the flag and
silently ignores it, always reporting the default profile, while `order submit` honors
it — so `doctor -p X` can verify one endpoint while the order goes to another. Profile
selection goes through the ALPACA_PROFILE environment variable, which both honor.
See the alpaca-trading-paper-trading-cli skill, rule 8.
"""

import json
import subprocess
import uuid
from dataclasses import dataclass
from typing import Optional

PAPER_TRADING_HOST = "https://paper-api.alpaca.markets"
CLI_TIMEOUT_SECONDS = 60


class LiveEndpointError(RuntimeError):
    """Raised when the CLI does not resolve to the paper endpoint. Never caught and
    downgraded to a warning — an unverified endpoint means no order is submitted."""


class CliUnavailableError(RuntimeError):
    """The `alpaca` binary is missing or unusable on this machine."""


@dataclass
class CliResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    error: Optional[str] = None


def _run(args: list[str], timeout: int = CLI_TIMEOUT_SECONDS) -> CliResult:
    """One place where the CLI is invoked, so every call gets the same timeout,
    UTF-8 decoding and exit-code handling. Exit codes: 0 ok, 1 error, 2 auth failure."""
    try:
        proc = subprocess.run(
            ["alpaca", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except FileNotFoundError:
        return CliResult(ok=False, error="'alpaca' CLI not found on PATH")
    except subprocess.TimeoutExpired:
        return CliResult(ok=False, error=f"alpaca CLI timed out after {timeout}s")

    return CliResult(
        ok=proc.returncode == 0,
        stdout=(proc.stdout or "").strip(),
        stderr=(proc.stderr or "").strip(),
        exit_code=proc.returncode,
        error=None if proc.returncode == 0 else (proc.stderr or "").strip()[:500],
    )


def verify_paper_endpoint() -> str:
    """Hard gate. Returns the resolved trading host, or raises.

    Called immediately before every submission rather than once at startup: the
    resolution depends on environment variables that a later step could change, so a
    check performed minutes earlier proves nothing about this order."""
    result = _run(["doctor"])
    if result.error and "not found on PATH" in result.error:
        raise CliUnavailableError(result.error)

    # doctor exits 1 when any check fails; a failed connectivity check is not something
    # to trade through even if the endpoint line happens to look right.
    if not result.ok:
        raise LiveEndpointError(
            f"alpaca doctor reported a failure (exit {result.exit_code}); refusing to submit. "
            f"stderr: {result.stderr[:300]}"
        )

    trading_line = next(
        (ln.strip() for ln in result.stdout.splitlines() if ln.strip().startswith("Trading:")),
        None,
    )
    if trading_line is None:
        raise LiveEndpointError("alpaca doctor output had no 'Trading:' line; cannot confirm paper endpoint")

    host = trading_line.split("Trading:", 1)[1].strip()
    if host != PAPER_TRADING_HOST:
        raise LiveEndpointError(
            f"CLI resolves to {host}, not the paper endpoint. Refusing to submit. "
            "Check ALPACA_LIVE_TRADE and the active profile's live_trade field."
        )
    return host


def build_legs_payload(spread) -> list[dict]:
    """Converts a SpreadOrder's legs into the CLI's --legs JSON. Enum values are taken
    via .value so the payload carries Alpaca's own wire strings, not Python repr."""
    return [
        {
            "symbol": leg.symbol,
            "ratio_qty": "1",
            "side": leg.side.value if hasattr(leg.side, "value") else str(leg.side),
            "position_intent": (
                leg.position_intent.value
                if hasattr(leg.position_intent, "value")
                else str(leg.position_intent)
            ),
        }
        for leg in spread.legs
    ]


def build_submit_args(spread, contracts: int, client_order_id: str, dry_run: bool = False) -> list[str]:
    """The exact argv for one atomic multi-leg submission.

    Built once and used for both the dry-run and the real submission, so the request
    body we log is provably the body we sent — not a reconstruction of it."""
    args = [
        "order", "submit",
        "--order-class", "mleg",
        "--qty", str(contracts),
        "--type", "limit",
        # net_price sign convention: positive = pay a debit, negative = receive a credit.
        # Alpaca's multi-leg limit_price is the net price for the whole spread and is
        # always sent as a positive magnitude; the legs' sides carry the direction.
        "--limit-price", f"{abs(round(spread.net_price, 2)):.2f}",
        "--time-in-force", "day",
        "--legs", json.dumps(build_legs_payload(spread), separators=(",", ":")),
        "--client-order-id", client_order_id,
    ]
    if dry_run:
        args.append("--dry-run")
    return args


def submit_spread_via_cli(spread, contracts: int) -> dict:
    """Verify endpoint -> dry-run -> submit, returning one audit-ready record.

    The dry-run is not decoration: it renders the request body the CLI would send
    without sending it, so a malformed legs payload surfaces before an order exists.
    Both the command and that body go into the returned record.

    A generated client_order_id makes the submission idempotent. If the call dies
    after Alpaca accepted the order but before we saw the response, the order is
    recoverable by that id instead of being blindly resubmitted."""
    endpoint = verify_paper_endpoint()
    client_order_id = f"oaa-{uuid.uuid4()}"  # oaa = options alpha agent

    preview_args = build_submit_args(spread, contracts, client_order_id, dry_run=True)
    preview = _run(preview_args)
    if not preview.ok:
        return {
            "submitted": False,
            "via": "alpaca_cli",
            "endpoint": endpoint,
            "client_order_id": client_order_id,
            "command": _redacted_command(preview_args),
            "error": f"dry-run rejected the request before submission: {preview.error}",
        }

    submit_args = build_submit_args(spread, contracts, client_order_id, dry_run=False)
    result = _run(submit_args)

    record = {
        "submitted": result.ok,
        "via": "alpaca_cli",
        "endpoint": endpoint,
        "client_order_id": client_order_id,
        "command": _redacted_command(submit_args),
        "request_body": _safe_json(preview.stdout),  # exactly what the dry-run rendered
        "exit_code": result.exit_code,
    }

    if not result.ok:
        record["error"] = result.error
        # Ambiguous failures must not be retried blind — the order may already exist.
        record["recover_with"] = f"alpaca order get-by-client-id --client-order-id {client_order_id}"
        return record

    response = _safe_json(result.stdout)
    record["response"] = response
    if isinstance(response, dict):
        record["order_id"] = response.get("id")
        record["status"] = response.get("status")
    return record


def get_broker_state() -> dict:
    """Ground truth for reconciliation, read through the CLI rather than the SDK.

    Deliberately a SECOND, independent path to the same facts the orchestrator already
    fetched via alpaca-py. A reconciliation that reads the same client the agent trusts
    proves nothing; two paths disagreeing is exactly the signal worth having."""
    positions = _run(["position", "list"])
    if not positions.ok:
        return {"ok": False, "error": positions.error}
    account = _run(["account", "get", "--jq", "{equity}"])
    if not account.ok:
        return {"ok": False, "error": account.error}

    parsed = _safe_json(positions.stdout)
    rows = parsed if isinstance(parsed, list) else (parsed or {}).get("positions") or []
    underlyings = set()
    for row in rows if isinstance(rows, list) else []:
        symbol = (row or {}).get("symbol") or ""
        # OCC option symbols carry the underlying as the leading alphabetic run.
        root = "".join(c for c in symbol[:6] if c.isalpha())
        if root:
            underlyings.add(root)

    equity_doc = _safe_json(account.stdout) or {}
    try:
        equity = float(equity_doc.get("equity"))
    except (TypeError, ValueError):
        return {"ok": False, "error": f"could not read equity from CLI: {equity_doc}"}

    return {"ok": True, "underlyings": sorted(underlyings), "equity": equity, "position_count": len(rows)}


def get_order_status(order_id: str) -> dict:
    """Post-submission lifecycle check, used by the audit trail rather than for control flow."""
    result = _run(["order", "get", "--order-id", order_id])
    if not result.ok:
        return {"ok": False, "error": result.error}
    return {"ok": True, "order": _safe_json(result.stdout)}


def _safe_json(text: str):
    """CLI output is JSON by default, but a warning line can precede it. Never let a
    parse failure lose the payload — keep the raw text instead."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start != -1:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                pass
        return {"unparsed_output": text[:2000]}


def _redacted_command(args: list[str]) -> str:
    """The command as run, for the audit log. No credentials appear in these argv lists —
    the CLI reads them from its own profile — but this is the single place to strip them
    if that ever changes."""
    return " ".join(["alpaca", *args])


if __name__ == "__main__":
    # Read-only self-check: proves the CLI is installed, authenticated and paper-resolved.
    # Submits nothing.
    try:
        host = verify_paper_endpoint()
        print(f"endpoint verified: {host}")
    except (LiveEndpointError, CliUnavailableError) as e:
        print(f"endpoint check FAILED: {e}")
        raise SystemExit(1)

    acct = _run(["account", "get", "--jq", "{status, equity, options_trading_level, buying_power}"])
    print(f"account: {acct.stdout if acct.ok else acct.error}")

    clock = _run(["clock", "--jq", "{is_open, next_open, next_close}"])
    print(f"clock: {clock.stdout if clock.ok else clock.error}")
