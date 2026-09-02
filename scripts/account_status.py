"""Read the competition account without being able to trade on it.

The repo has one active Alpaca CLI profile and one pair of env keys, and they drive
everything, execution included. Re-pointing either at the competition account would also
re-point src/execution.py and `scheduler --live`, so an ordinary local experiment could
submit a real order to the account being judged. The dev account exists to absorb that.

So the competition account gets its own named CLI profile and is never made active. This
script passes --profile explicitly on each call and imports nothing from the execution
path - no src.execution, no src.orchestrator, no src.scheduler. It calls three read
endpoints and prints. There is no code path from here to an order.

Create the profile once (the CLI prompts; the key never passes through this repo):

    alpaca profile login --api-key --paper --name comp

Then:

    python scripts/account_status.py          # profile "comp"
    python scripts/account_status.py paper    # any other profile
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.alpaca_cli import _run, _safe_json, underlying_root

# Read-only verbs only. Kept as a literal allow-list rather than a convention, because the
# whole point of this file is that it cannot reach a write.
READ_ONLY = {("account", "get"), ("position", "list"), ("order", "list")}


def read(profile: str, *args: str):
    if tuple(args[:2]) not in READ_ONLY:
        raise SystemExit(f"refusing non-read command: {' '.join(args)}")
    return _safe_json(_run([*args, "--profile", profile]).stdout)


def main() -> None:
    profile = sys.argv[1] if len(sys.argv) > 1 else "comp"
    print(f"\n  profile: {profile}")

    acct = read(profile, "account", "get") or {}
    equity = float(acct.get("equity") or 0)
    if not equity:
        print(f"  could not read the account. Does the profile exist?"
              f"  ->  alpaca profile login --api-key --paper --name {profile}\n")
        return

    last = float(acct.get("last_equity") or 0)
    pnl = equity - 100_000
    day = equity - last if last else 0.0
    print(f"  equity   ${equity:,.2f}   since open {pnl:+,.2f} ({pnl/1000:+.2f}%)"
          f"   today {day:+,.2f}")
    print(f"  cash     ${float(acct.get('cash') or 0):,.2f}")

    positions = read(profile, "position", "list") or []
    print(f"\n  {len(positions)} option legs open")
    total = 0.0
    for p in sorted(positions, key=lambda x: x["symbol"]):
        upl = float(p.get("unrealized_pl") or 0)
        total += upl
        print(f"    {p['symbol']:<24} {p['side']:<6} {p['qty']:>3}"
              f"   entry {float(p['avg_entry_price']):>6.2f}"
              f"   now {float(p['current_price']):>6.2f}   {upl:>+8.2f}")
    if positions:
        roots = sorted({underlying_root(p["symbol"]) for p in positions})
        print(f"    {'':<24} {'':<6} {'':>3}   {'':>12}   unrealized {total:>+8.2f}")
        print(f"    underlyings held: {', '.join(roots)}")

    orders = read(profile, "order", "list", "--status", "open") or []
    print(f"\n  {len(orders)} resting orders")
    for o in orders:
        print(f"    {o.get('symbol') or o.get('id')}   {o.get('status')}")
    print()


if __name__ == "__main__":
    main()
