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
