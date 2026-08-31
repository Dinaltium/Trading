"""
Cross-cycle state.

This exists because of a specific defect. The execution circuit breaker in guards.py was
written as an in-memory dataclass, and the agent runs as `python -m src.scheduler --once`
on a GitHub Actions cron — a brand-new process every 15 minutes. In-memory counters die
with the process, so a breaker that trips on failure 3 would have been reset to zero before
failure 2 ever happened. It could never fire. Anything that must survive a restart has to
live on disk.

The design rule for what belongs here: state that CANNOT be re-derived from an
authoritative source. Positions, equity and market hours are all re-read from Alpaca every
cycle and are deliberately NOT stored — a cached copy of something the broker already knows
is a second source of truth waiting to disagree with the first. What lives here is only the
agent's own operational history: how many times execution has failed in a row, when the last
cycle ran, and whether a human has latched the breaker.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

STATE_PATH = Path(__file__).resolve().parent.parent / "logs" / "agent_state.json"

# A cycle should run every 15 minutes during market hours. Three missed cycles means
# something is wrong with the scheduler itself, which the agent cannot detect from inside
# a single run — only by noticing how long ago the previous one was.
HEARTBEAT_STALE_AFTER = timedelta(minutes=50)


@dataclass
class AgentState:
    consecutive_execution_failures: int = 0
    breaker_tripped: bool = False
    breaker_failures_at_trip: int = 0
    last_execution_error: Optional[str] = None
    last_cycle_at: Optional[str] = None       # ISO8601 UTC
    last_submission_at: Optional[str] = None
    cycles_recorded: int = 0
    # Per-underlying loss streak, reset by any winning close. Belongs here rather than being
    # re-derived from the broker because Alpaca reports open positions, not the sequence of
    # closed outcomes that produced them - and the agent's own trade history is exactly the
    # kind of operational state that cannot be re-read from an authoritative source.
    consecutive_losses_by_underlying: dict = field(default_factory=dict)

    # --- persistence ---

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "AgentState":
        """A missing or corrupt state file yields a fresh state rather than an exception.
        Losing operational history is survivable; refusing to trade because a JSON file was
        half-written during a killed push is not."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path = STATE_PATH) -> None:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")

    # --- breaker, persisted across processes ---

    def record_execution_failure(self, error: str, max_consecutive: int = 3) -> None:
        self.consecutive_execution_failures += 1
        self.last_execution_error = error[:500]
        if self.consecutive_execution_failures >= max_consecutive and not self.breaker_tripped:
            self.breaker_tripped = True
            self.breaker_failures_at_trip = self.consecutive_execution_failures

    def record_execution_success(self, when: Optional[str] = None) -> None:
        """Clears the counter but deliberately NOT the tripped latch. A breaker that
        un-trips on the first success turns an outage into an oscillation: fail, fail, fail,
        trip, succeed once, resume, fail again. Clearing it is a human decision."""
        self.consecutive_execution_failures = 0
        self.last_execution_error = None
        self.last_submission_at = when

    # --- adaptive restriction, persisted across processes -----------------------------

    def record_closed_trade(self, underlying: str, realised_pnl: float) -> None:
        """A losing close extends that underlying's streak; any win clears it.

        Deliberately keyed per underlying rather than globally: three losses on one name is
        evidence about that name, while three losses spread across four names is evidence
        about the market and would halt everything at the worst possible moment."""
        if not underlying:
            return
        streaks = dict(self.consecutive_losses_by_underlying or {})
        if realised_pnl < 0:
            streaks[underlying] = streaks.get(underlying, 0) + 1
        else:
            streaks.pop(underlying, None)
        self.consecutive_losses_by_underlying = streaks

    def is_restricted(self, underlying: str, max_consecutive_losses: int = 3) -> bool:
        """Whether NEW entries in this underlying are barred. Never consulted for exits:
        a rule that stops the agent opening a position must not also stop it closing one."""
        return (self.consecutive_losses_by_underlying or {}).get(underlying, 0) >= max_consecutive_losses

    def restriction_detail(self, underlying: str) -> str:
        n = (self.consecutive_losses_by_underlying or {}).get(underlying, 0)
        return f"{n} consecutive losing closes on {underlying}"

    def reset_breaker(self) -> None:
        self.consecutive_execution_failures = 0
        self.breaker_tripped = False
        self.breaker_failures_at_trip = 0
        self.last_execution_error = None

    # --- heartbeat ---

    def note_cycle(self, when: datetime) -> None:
        self.last_cycle_at = when.astimezone(timezone.utc).isoformat()
        self.cycles_recorded += 1

    def heartbeat(self, now: datetime) -> dict:
        """How long since the previous cycle. TradeTrap lists heartbeat monitoring as the
        execution-layer mitigation for latency flooding and DoS; here it also catches the
        duller failure of a cron that silently stopped firing."""
        if not self.last_cycle_at:
            return {"first_cycle": True, "stale": False, "minutes_since_last_cycle": None}
        try:
            previous = datetime.fromisoformat(self.last_cycle_at)
        except ValueError:
            return {"first_cycle": False, "stale": False, "minutes_since_last_cycle": None}
        gap = (now.astimezone(timezone.utc) - previous).total_seconds() / 60.0
        return {
            "first_cycle": False,
            "stale": gap > HEARTBEAT_STALE_AFTER.total_seconds() / 60.0,
            "minutes_since_last_cycle": round(gap, 1),
            "previous_cycle_at": self.last_cycle_at,
        }

    def as_record(self) -> dict:
        """What the audit log carries, so a restart is legible from the log alone."""
        return {
            "cycles_recorded": self.cycles_recorded,
            "consecutive_execution_failures": self.consecutive_execution_failures,
            "breaker_tripped": self.breaker_tripped,
            "last_execution_error": self.last_execution_error,
            "last_submission_at": self.last_submission_at,
        }


if __name__ == "__main__":
    state = AgentState.load()
    print(json.dumps(asdict(state), indent=2))
    print("heartbeat:", state.heartbeat(datetime.now(timezone.utc)))
