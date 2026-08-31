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

from src.audit_log import push_audit_log, write_exit_record
from src.live_settings import fetch_live_settings
from src.orchestrator import run_cycle
from src.positions import manage_open_positions

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
    if settings.trading_mode == "paused":
        print(f"[{datetime.now().isoformat()}] trading paused via /admin, skipping cycle entirely")
        return

    # Exits run BEFORE entries and in every non-paused mode. Managing existing risk is not
    # something a kill switch should be able to turn off while positions are still open.
    if settings.may_close_positions:
        exits = manage_open_positions(dry_run=dry_run)
        write_exit_record(exits, dry_run=dry_run)  # closes belong in the audit log, not just stdout
        if exits.get("ok"):
            for closed in exits.get("closed") or []:
                print(f"  -> CLOSED {closed['spread']}: {closed['reason']}")
            for held in exits.get("held") or []:
                print(f"  -> holding {held['spread']}: {held['reason']}")
        else:
            print(f"  -> exit pass failed: {exits.get('error')}")

    if not settings.may_open_new_positions:
        print(f"[{datetime.now().isoformat()}] mode={settings.trading_mode}: exits only, no new entries")
        if not test_mode:
            push_audit_log()
        return
    print(f"[{datetime.now().isoformat()}] mode={settings.trading_mode}  live_provider={settings.active_model_provider}  underlyings={settings.underlyings}")

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


def start_session(
    dry_run: bool = True,
    interval_minutes: int = INTERVAL_MINUTES,
    max_minutes: int = 330,
):
    """One process per market session, instead of one CI job per cycle.

    GitHub's scheduler drops short-interval crons under load — a `*/15` schedule asked for
    ~36 firings across Aug 29 and Aug 31 and delivered zero. Depending on 26 separate cron
    events landing every day is a bet we lost. This mode needs exactly ONE of them to land:
    the job wakes up, then drives the 15-minute cadence itself for the rest of the session.

    Shuts down on whichever comes first:
      - the market has been open and is now closed (normal end of day), or
      - max_minutes elapsed — kept under the 6h GitHub-hosted job ceiling so the run ends
        green rather than being killed by the runner and showing a red X to judges.
    """
    scheduler = BlockingScheduler()
    started_at = datetime.now()
    seen_open = False

    def tick():
        nonlocal seen_open

        elapsed = (datetime.now() - started_at).total_seconds() / 60
        if elapsed >= max_minutes:
            print(f"[{datetime.now().isoformat()}] session budget of {max_minutes}min reached, shutting down cleanly")
            scheduler.shutdown(wait=False)
            return

        load_dotenv(override=True)
        client = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)
        if market_is_open(client):
            seen_open = True
        elif seen_open:
            # Only exit on a close we actually traded through. A job that starts a few minutes
            # before the bell must keep polling, not mistake "not open yet" for "day over".
            print(f"[{datetime.now().isoformat()}] market closed after an open session, shutting down")
            scheduler.shutdown(wait=False)
            return

        run_all_cycles(dry_run=dry_run, test_mode=False)

    scheduler.add_job(tick, "interval", minutes=interval_minutes, next_run_time=datetime.now())
    print(f"session runner starting: every {interval_minutes}min, dry_run={dry_run}, budget={max_minutes}min")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("session runner stopped")


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

    def _flag_value(name: str, default: int) -> int:
        if name not in sys.argv:
            return default
        return int(sys.argv[sys.argv.index(name) + 1])

    if "--once" in sys.argv:
        # single-shot mode: run exactly one tick and exit. Kept for manual triggers and
        # local debugging. It is no longer how the workflow drives the day — see --session.
        run_all_cycles(dry_run=dry_run, test_mode=test_mode)
    elif "--session" in sys.argv:
        # session mode: one CI job covers a whole market session, driving the 15-min cadence
        # itself. Depends on one cron firing per half-session rather than 26 per day.
        start_session(dry_run=dry_run, max_minutes=_flag_value("--max-minutes", 330))
    else:
        # long-running local mode (BlockingScheduler) — still usable for local dev/testing.
        start(dry_run=dry_run, test_mode=test_mode)
