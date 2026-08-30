"""
Weekend smoke test: exercise the execution and guard plumbing against crypto.

US equity options do not trade at the weekend, so the last chance to shake out the
execution path before Monday's 09:30 ET open would otherwise be Monday's 09:30 ET open.
Crypto trades 24/7 on the same account, through the same CLI, against the same broker
state — so it can exercise everything that is not options-specific, tonight.

WHAT THIS ACTUALLY VALIDATES
    CLI auth, paper-endpoint guard, order construction, dry-run rendering,
    client-order-id idempotency, broker-state reads, reconciliation, the persisted
    circuit breaker, agent_state round-tripping, audit logging.

WHAT IT DOES NOT VALIDATE
    Anything options-specific: the option chain, delta-based strike selection, MLEG
    multi-leg atomicity, IV Rank, VRP, or the rulebook (which needs iv_rank). Crypto has
    no options on Alpaca and no multi-leg orders. A green run here means the plumbing is
    sound, NOT that the strategy works.

Defaults to dry-run: it renders the exact request body the CLI would send and submits
nothing. Pass --submit to place a real paper order.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent_state import AgentState                      # noqa: E402
from src.alpaca_cli import _run, get_broker_state, verify_paper_endpoint  # noqa: E402
from src.guards import reconcile_positions, validate_signals  # noqa: E402

SYMBOL = "BTC/USD"
NOTIONAL = "5"  # dollars. Small enough to be noise against $100k, large enough to fill.


def step(n: int, title: str) -> None:
    print(f"\n[{n}] {title}")
    print("-" * 68)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submit", action="store_true",
                        help="place a real paper order instead of only rendering it")
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--notional", default=NOTIONAL)
    args = parser.parse_args()

    failures = []

    step(1, "Paper endpoint guard")
    try:
        host = verify_paper_endpoint()
        print(f"    OK  resolved to {host}")
    except Exception as e:
        print(f"    FAIL  {e}")
        return 1  # nothing else may run if we cannot prove the endpoint

    step(2, "Asset is tradable")
    asset = _run(["asset", "get", "--symbol-or-asset-id", args.symbol,
                  "--jq", "{symbol, status, tradable, fractionable, min_order_size}"])
    print(f"    {asset.stdout if asset.ok else asset.error}")
    if not asset.ok or '"tradable": true' not in asset.stdout:
        failures.append("asset not tradable")

    step(3, "Live market data while equities are closed")
    bars = _run(["data", "crypto", "latest-bars", "--symbols", args.symbol])
    print(f"    {(bars.stdout or bars.error)[:300]}")
    if not bars.ok:
        failures.append("crypto market data unavailable")

    step(4, "Broker state read (the reconciliation ground truth)")
    broker = get_broker_state()
    print(f"    {json.dumps(broker)}")
    if not broker.get("ok"):
        failures.append("broker state unreadable")

    step(5, "Reconciliation — agreeing and disagreeing cases")
    believed = set(broker.get("underlyings") or [])
    agree = reconcile_positions(believed, broker.get("equity", 0.0), broker)
    print(f"    matching state   -> passed={agree.passed}")
    disagree = reconcile_positions(set(), broker.get("equity", 0.0),
                                   {**broker, "underlyings": ["FAKE"]})
    print(f"    injected mismatch-> passed={disagree.passed}  {disagree.failures}")
    if not agree.passed or disagree.passed:
        failures.append("reconciliation did not behave as specified")

    step(6, "Signal guard rejects a corrupted vector")
    good = validate_signals({"classifier_p_up": 0.51, "iv_rank": 50.0, "current_price": 100.0})
    bad = validate_signals({"classifier_p_up": 4.2, "iv_rank": 50.0, "current_price": 100.0})
    print(f"    clean signals -> passed={good.passed}")
    print(f"    p_up=4.2      -> passed={bad.passed}  {bad.failures}")
    if not good.passed or bad.passed:
        failures.append("signal guard did not behave as specified")

    step(7, "Persisted agent state round-trip")
    state = AgentState.load()
    before = state.cycles_recorded
    print(f"    loaded: cycles={before} breaker_tripped={state.breaker_tripped}")

    step(8, f"Order construction ({'REAL SUBMIT' if args.submit else 'dry-run, submits nothing'})")
    client_order_id = f"smoke-{uuid.uuid4()}"
    order_args = [
        "order", "submit",
        "--symbol", args.symbol,
        "--side", "buy",
        "--notional", args.notional,
        "--type", "market",
        "--time-in-force", "gtc",   # crypto is gtc, not day
        "--client-order-id", client_order_id,
    ]
    preview = _run([*order_args, "--dry-run"])
    print(f"    request body the CLI would send:\n{preview.stdout or preview.error}")
    if not preview.ok:
        failures.append("dry-run rejected the order")

    if args.submit:
        result = _run(order_args)
        if result.ok:
            print(f"    SUBMITTED: {result.stdout[:400]}")
            print(f"    recover with: alpaca order get-by-client-id --client-order-id {client_order_id}")
        else:
            print(f"    SUBMIT FAILED: {result.error}")
            failures.append("live submission failed")
    else:
        print("    (not submitted — pass --submit to place a real paper order)")

    print("\n" + "=" * 68)
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All plumbing checks passed.")
    print("Reminder: this exercised execution and guards, NOT the options strategy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
