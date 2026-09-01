"""
Cross-cycle state. These tests exist because the circuit breaker was originally written as
an in-memory dataclass while the agent runs as a fresh process every 15 minutes — so the
breaker could never actually trip. Every test here is about surviving a restart.
"""

from datetime import datetime, timedelta, timezone

from src.agent_state import AgentState


def test_state_survives_a_restart(tmp_path):
    path = tmp_path / "agent_state.json"
    first = AgentState()
    first.record_execution_failure("connection reset")
    first.record_execution_failure("connection reset")
    first.save(path)

    # A different process entirely: nothing shared but the file.
    second = AgentState.load(path)
    assert second.consecutive_execution_failures == 2
    assert not second.breaker_tripped

    second.record_execution_failure("connection reset")
    second.save(path)

    third = AgentState.load(path)
    assert third.breaker_tripped, "breaker must trip on failures spread across processes"
    assert third.breaker_failures_at_trip == 3


def test_missing_file_yields_fresh_state(tmp_path):
    state = AgentState.load(tmp_path / "nope.json")
    assert state.cycles_recorded == 0
    assert not state.breaker_tripped


def test_corrupt_file_yields_fresh_state_rather_than_raising(tmp_path):
    """A half-written file must not stop the agent from running."""
    path = tmp_path / "agent_state.json"
    path.write_text('{"consecutive_execution', encoding="utf-8")
    assert AgentState.load(path).cycles_recorded == 0


def test_unknown_fields_are_ignored(tmp_path):
    """Forward compatibility: an older process reading a newer state file."""
    path = tmp_path / "agent_state.json"
    path.write_text('{"cycles_recorded": 7, "invented_field": 1}', encoding="utf-8")
    assert AgentState.load(path).cycles_recorded == 7


def test_success_clears_the_counter_but_not_the_latch():
    """A breaker that un-trips on one success turns an outage into an oscillation."""
    state = AgentState()
    for _ in range(3):
        state.record_execution_failure("boom")
    assert state.breaker_tripped

    state.record_execution_success()
    assert state.consecutive_execution_failures == 0
    assert state.breaker_tripped, "clearing a tripped breaker must be a human decision"

    state.reset_breaker()
    assert not state.breaker_tripped


def test_breaker_does_not_re_trip_and_overwrite_its_own_record():
    state = AgentState()
    for _ in range(5):
        state.record_execution_failure("boom")
    assert state.breaker_failures_at_trip == 3, "the count at trip time is frozen"


def test_heartbeat_first_cycle():
    hb = AgentState().heartbeat(datetime.now(timezone.utc))
    assert hb["first_cycle"]
    assert not hb["stale"]


def test_heartbeat_detects_a_missed_schedule():
    now = datetime.now(timezone.utc)
    state = AgentState()
    state.note_cycle(now - timedelta(minutes=90))
    hb = state.heartbeat(now)
    assert hb["stale"]
    assert hb["minutes_since_last_cycle"] == 90.0


def test_heartbeat_normal_cadence_is_not_stale():
    now = datetime.now(timezone.utc)
    state = AgentState()
    state.note_cycle(now - timedelta(minutes=15))
    assert not state.heartbeat(now)["stale"]


def test_cycle_counter_increments(tmp_path):
    path = tmp_path / "agent_state.json"
    for _ in range(3):
        state = AgentState.load(path)
        state.note_cycle(datetime.now(timezone.utc))
        state.save(path)
    assert AgentState.load(path).cycles_recorded == 3


# --- adaptive restriction ---------------------------------------------------------------
# Adapt only toward restriction. A run of losses on one name is the agent's own evidence
# that it is reading that name badly; widening exposure on a winning streak is the same
# reasoning run backwards, and five days of data cannot support it.

def test_losing_closes_accumulate_per_underlying():
    from src.agent_state import AgentState

    s = AgentState()
    for _ in range(3):
        s.record_closed_trade("SPY", -120.0)
    assert s.consecutive_losses_by_underlying["SPY"] == 3
    assert s.is_restricted("SPY", max_consecutive_losses=3)


def test_a_win_clears_the_streak():
    from src.agent_state import AgentState

    s = AgentState()
    s.record_closed_trade("SPY", -120.0)
    s.record_closed_trade("SPY", -80.0)
    s.record_closed_trade("SPY", 40.0)
    assert not s.is_restricted("SPY", max_consecutive_losses=3)
    assert "SPY" not in s.consecutive_losses_by_underlying


def test_restriction_does_not_leak_across_underlyings():
    """Three losses spread over three names is evidence about the market, not about any one
    name. Halting everything on it would be the worst possible response."""
    from src.agent_state import AgentState

    s = AgentState()
    for u in ("SPY", "QQQ", "IWM"):
        s.record_closed_trade(u, -100.0)
    for u in ("SPY", "QQQ", "IWM", "AAPL"):
        assert not s.is_restricted(u, max_consecutive_losses=3)


def test_restriction_survives_the_restart_between_cycles(tmp_path):
    """The agent runs as a fresh process every tick. A streak held in memory would reset to
    zero before the third loss ever happened - the same defect that made the execution
    circuit breaker unable to fire."""
    from src.agent_state import AgentState

    path = tmp_path / "state.json"
    s = AgentState()
    for _ in range(3):
        s.record_closed_trade("AAPL", -50.0)
    s.save(path)

    reloaded = AgentState.load(path)
    assert reloaded.is_restricted("AAPL", max_consecutive_losses=3)


def test_break_even_close_is_not_a_loss():
    from src.agent_state import AgentState

    s = AgentState()
    s.record_closed_trade("SPY", 0.0)
    assert s.consecutive_losses_by_underlying.get("SPY", 0) == 0


# --- operator modes -----------------------------------------------------------------------

def test_flatten_stops_new_entries_but_still_permits_closing():
    from src.live_settings import LiveSettings

    s = LiveSettings(trading_mode="flatten")
    assert not s.may_open_new_positions
    assert s.may_close_positions
    assert s.should_flatten


def test_paused_is_the_only_mode_that_also_stops_closing():
    """paused refuses everything, which is the wrong tool with positions open — it stops the
    agent taking risk and simultaneously stops it managing the risk it took."""
    from src.live_settings import LiveSettings, TRADING_MODES

    for mode in TRADING_MODES:
        s = LiveSettings(trading_mode=mode)
        assert s.may_close_positions is (mode != "paused"), mode


def test_no_mode_lets_the_operator_choose_a_trade():
    """The boundary that keeps this autonomous: an operator can stop everything and can
    never pick anything. Only 'running' opens positions, and it opens what the rulebook
    mandates, not what a human asked for."""
    from src.live_settings import LiveSettings, TRADING_MODES

    opening = [m for m in TRADING_MODES if LiveSettings(trading_mode=m).may_open_new_positions]
    assert opening == ["running"]


def test_unreadable_settings_never_resume_trading():
    """The kill switch must not fail open.

    fetch_live_settings falls back when the settings cannot be read. It used to fall back to
    the module default, whose trading_mode is "running" — so an operator could set flatten,
    a single network blip could drop the next fetch, and the agent would silently resume
    trading against an explicit instruction to stop. exit_only halts new entries while still
    running stop-loss and take-profit, so a transient failure costs a cycle of entries and can
    never override a halt."""
    from src.live_settings import DEFAULT_SETTINGS, UNREADABLE_SETTINGS

    assert not UNREADABLE_SETTINGS.may_open_new_positions
    assert UNREADABLE_SETTINGS.may_close_positions
    assert DEFAULT_SETTINGS.may_open_new_positions, "the normal default still trades"


def test_resting_orders_do_not_read_as_phantom_holdings():
    """Guard 4 compares the agent's position map against the broker's. open_underlyings now
    includes names with a resting order, which the broker does not report as a position — so
    reconciliation must be handed held_underlyings, or every working order looks like a
    holding the broker has lost."""
    from src.guards import reconcile_positions
    from src.risk_gate import AccountState

    acct = AccountState(
        equity=100_000.0, open_risk_dollars=0.0,
        open_underlyings={"SPY", "DIA"},   # DIA has only a resting order
        daily_pnl_pct=0.0, held_underlyings={"SPY"},
    )
    broker = {"ok": True, "underlyings": ["SPY"], "equity": 100_000.0}

    assert reconcile_positions(acct.held_underlyings, acct.equity, broker).passed
    noisy = reconcile_positions(acct.open_underlyings, acct.equity, broker)
    assert noisy.warnings, "the old wiring would have warned about a phantom DIA"
