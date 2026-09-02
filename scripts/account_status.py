"""Read the competition account over a path that cannot place an order.

The repo drives execution two ways - the active Alpaca CLI profile (src/alpaca_cli.py) and
the ALPACA_API_KEY/ALPACA_SECRET_KEY pair (src/execution.py, src/scheduler.py). Pointing
either at the competition account so a balance can be read would also point the execution
path at it, and a routine local experiment could then submit a real order to the account
being judged. The dev account exists to absorb that.

So this reads neither. Keys live in .env.local under their own COMP_ names, which the
execution path never looks up, and the calls are plain HTTP GETs against three read
endpoints. There is no CLI profile involved, no src.execution or src.scheduler import, and
no verb here other than GET.

Create .env.local (gitignored via .env.*) with the competition account's paper keys:

    COMP_ALPACA_API_KEY=...
    COMP_ALPACA_SECRET_KEY=...

Then:

    python scripts/account_status.py
"""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env.local"

# Paper, hardcoded. Not read from config and not overridable by an env var, so this file
# cannot be pointed at the live endpoint by editing something else.
BASE = "https://paper-api.alpaca.markets/v2"


def get(path: str, key: str, secret: str, **params):
    r = requests.get(
        f"{BASE}/{path}",
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        params=params,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def underlying(symbol: str) -> str:
    """OCC symbols are ROOT + 6-digit date + C/P + 8-digit strike, so the root is whatever
    precedes the first digit."""
    for i, ch in enumerate(symbol):
        if ch.isdigit():
            return symbol[:i]
    return symbol


def main() -> None:
    if not ENV.exists():
        print(f"\n  no .env.local - create it with COMP_ALPACA_API_KEY / "
              f"COMP_ALPACA_SECRET_KEY\n  ({ENV})\n")
        return
    load_dotenv(ENV, override=True)
    key, secret = os.getenv("COMP_ALPACA_API_KEY"), os.getenv("COMP_ALPACA_SECRET_KEY")
    if not key or not secret:
        print("\n  .env.local exists but COMP_ALPACA_API_KEY / COMP_ALPACA_SECRET_KEY "
              "are not both set\n")
        return

    try:
        acct = get("account", key, secret)
    except requests.HTTPError as exc:
        print(f"\n  could not read the account: {exc}\n")
        return

    equity = float(acct.get("equity") or 0)
    last = float(acct.get("last_equity") or 0)
    pnl = equity - 100_000
    print(f"\n  account  {acct.get('account_number')}   status {acct.get('status')}")
    today = f"   today {equity - last:+,.2f}" if last else ""
    print(f"  equity   ${equity:,.2f}   since open {pnl:+,.2f} ({pnl/1000:+.2f}%){today}")
    print(f"  cash     ${float(acct.get('cash') or 0):,.2f}")

    positions = get("positions", key, secret)
    print(f"\n  {len(positions)} option legs open")
    total = 0.0
    for p in sorted(positions, key=lambda x: x["symbol"]):
        upl = float(p.get("unrealized_pl") or 0)
        total += upl
        print(f"    {p['symbol']:<24} {p['side']:<6} {p['qty']:>3}"
              f"   entry {float(p['avg_entry_price']):>6.2f}"
              f"   now {float(p['current_price']):>6.2f}   {upl:>+8.2f}")
    if positions:
        roots = sorted({underlying(p["symbol"]) for p in positions})
        print(f"    {'':<24} {'':<6} {'':>3}   {'':>12}   unrealized {total:>+8.2f}")
        print(f"    underlyings held: {', '.join(roots)}")

    orders = get("orders", key, secret, status="open", nested="true")
    print(f"\n  {len(orders)} resting orders")
    for o in orders:
        legs = o.get("legs") or []
        label = o.get("symbol") or (underlying(legs[0]["symbol"]) if legs else o.get("id"))
        print(f"    {label}   {o.get('status')}   {len(legs)} legs"
              f"   submitted {o.get('submitted_at', '')[:19]}")
    print()


if __name__ == "__main__":
    main()
