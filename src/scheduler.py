"""
Runs orchestrator.run_cycle() on a fixed interval during US equity market hours.
Market-hours check uses Alpaca's own clock endpoint rather than hand-rolled timezone
math, so it stays correct across holidays/early closes without extra bookkeeping.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime

from alpaca.trading.client import TradingClient
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from src.audit_log import push_audit_log
from src.live_settings import fetch_live_settings
from src.orchestrator import run_cycle

INTERVAL_MINUTES = 15
CYCLE_TIMEOUT_SECONDS = 90  # alpaca-py sets no request timeout anywhere in its REST layer
                            # (confirmed empirically — grep found none in common/rest.py), so a
                            # stalled connection hangs indefinitely with no built-in recovery.
                            # This is the outer safety net: one stuck network call can't freeze
                            # the whole scheduler forever. See BRAINSTORM.md weekend soak-test log.


def market_is_open(trading_client: TradingClient) -> bool:
    clock = trading_client.get_clock()
    return bool(clock.is_open)


def run_all_cycles(dry_run: bool = True, test_mode: bool = False):
    """test_mode=True bypasses the market-hours gate — for weekend soak-testing only.
    Never set True once the loop is running against a real submission window."""
    load_dotenv(override=True)
    trading_client = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)

    if not test_mode and not market_is_open(trading_client):
        print(f"[{datetime.now().isoformat()}] market closed, skipping cycle")
        return

    settings = fetch_live_settings()  # pulled fresh every tick — see src/live_settings.py
    if settings.trading_paused:
        print(f"[{datetime.now().isoformat()}] trading paused via /admin, skipping cycle")
        return
    print(f"[{datetime.now().isoformat()}] live_provider={settings.active_model_provider}  underlyings={settings.underlyings}")

    for underlying in settings.underlyings:
        print(f"[{datetime.now().isoformat()}] running cycle for {underlying} (dry_run={dry_run})")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                # record_history=not test_mode: by this point a non-test run has already passed
                # the market_is_open() check above, so only genuine market-hours cycles append to
                # the IV history. Weekend soak tests must not pollute it.
                future = pool.submit(
                    run_cycle, underlying, dry_run, settings.active_model_provider, not test_mode
                )
                result = future.result(timeout=CYCLE_TIMEOUT_SECONDS)
            decision = (result.get("live_decision") or {}).get("selected_strategy", "n/a")
            verdict = (result.get("risk_gate_verdict") or {}).get("reason", "n/a")
            print(f"  -> decision={decision}  risk_gate={verdict}")
        except FutureTimeoutError:
            print(f"  -> TIMEOUT: cycle for {underlying} exceeded {CYCLE_TIMEOUT_SECONDS}s, abandoning this cycle "
                  f"(underlying thread keeps running in the background until its stalled call eventually resolves "
                  f"or the process exits — Python cannot forcibly kill a thread, only stop waiting on it)")
        except Exception as e:
            print(f"  -> ERROR in cycle for {underlying}: {e}")

    if not test_mode:
        # push once per tick (not per underlying) — see audit_log.push_audit_log docstring.
        # Never pushes during weekend/test_mode soak runs, to keep the repo history meaningful.
        pushed = push_audit_log()
        print(f"  -> audit log pushed to GitHub: {pushed}")


def start(dry_run: bool = True, test_mode: bool = False, interval_minutes: int = INTERVAL_MINUTES):
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_all_cycles,
        "interval",
        minutes=interval_minutes,
        kwargs={"dry_run": dry_run, "test_mode": test_mode},
        next_run_time=datetime.now(),
    )
    print(f"scheduler starting: every {interval_minutes}min, dry_run={dry_run}, test_mode={test_mode}. Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("scheduler stopped")


if __name__ == "__main__":
    import sys

    test_mode = "--test-mode" in sys.argv
    dry_run = "--live" not in sys.argv  # default safe: dry_run=True unless --live is explicit

    if "--once" in sys.argv:
        # single-shot mode: run exactly one tick and exit. This is what GitHub Actions
        # calls on its own 15-min cron — the recurrence lives in the workflow schedule,
        # not in a long-running process, so this doesn't need your laptop open at all.
        run_all_cycles(dry_run=dry_run, test_mode=test_mode)
    else:
        # long-running local mode (BlockingScheduler) — still usable for local dev/testing.
        start(dry_run=dry_run, test_mode=test_mode)
