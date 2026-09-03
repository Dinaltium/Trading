# Brightline — architecture

> A bright-line rule admits no judgment. Neither does ours.

This is the system as it actually runs, not as it was designed. Where the two differ, the
difference is stated. Companion documents: [`graveyard.md`](graveyard.md) for every defect
this agent has had, [`handover.md`](handover.md) for how to run it,
[`architecture.svg`](architecture.svg) for the one-page picture.

---

## The claim the whole design serves

**A language model may decline a trade the rules mandate. It can never propose one they
don't.**

Everything below exists to make that sentence true by construction rather than by intention.
The model's output is one of five values, four of which the rulebook already decided are
legal for the current signals, and the fifth is "cash". There is no path from model text to a
broker order that does not pass through code that recomputes the answer independently.

---

## One cycle

A cycle runs every 15 minutes, per underlying, during market hours. Four underlyings —
SPY, QQQ, IWM, DIA — so a session produces four cycles per tick.

```
  ┌─ SIGNALS ──────────────────────────────────────────────────────────┐
  │  direction.py   LightGBM, isotonic-calibrated → P(Up)              │
  │  iv_rank.py     IV Rank + percentile from our own recorded history │
  │                 + VRP, market regime, days-to-earnings             │
  └────────────────────────────┬───────────────────────────────────────┘
                               │
                       GUARD 1 · signal validation
                       out of range / NaN / inconsistent → no model is called
                               │
  ┌─ MODELS (parallel) ────────▼───────────────────────────────────────┐
  │  groq         LIVE — its answer is the only one that can execute   │
  │  featherless  shadow — recorded, scored, never touches the account │
  │  mistral      shadow — recorded, scored, never touches the account │
  └────────────────────────────┬───────────────────────────────────────┘
                               │
                       GUARD 2 · faithfulness
                       a signal figure quoted but never handed over → reject
                               │
                       GUARD 3 · cross-model agreement (records, does not block)
                               │
  ┌─ RULEBOOK ─────────────────▼───────────────────────────────────────┐
  │  rulebook_strategy(iv_rank, p_up, iv_trusted) recomputed in Python │
  │  from the RAW signals — never from the model's summary of them.    │
  │  Model answer ≠ mandate and ≠ cash  →  off-book, rejected          │
  └────────────────────────────┬───────────────────────────────────────┘
                               │
  ┌─ RISK GATE (zero AI) ──────▼───────────────────────────────────────┐
  │  quarter-Kelly off the CALIBRATED classifier probability           │
  │  ≤2% equity per trade · ≤10% total open risk                       │
  │  one position per underlying · ≤4 concurrent underlyings           │
  │  5% daily drawdown halt · premium-selling halt at IV rank ≥90      │
  │  adaptive restriction after 3 consecutive losses on a name         │
  └────────────────────────────┬───────────────────────────────────────┘
                               │
                       GUARD 4 · reconciliation
                       internal position map vs a second independent broker read
                               │
  ┌─ EXECUTION ────────────────▼───────────────────────────────────────┐
  │  verify_paper_endpoint()  — `alpaca doctor`, out of process        │
  │  dry-run build → ONE atomic MLEG order → client_order_id           │
  └────────────────────────────┬───────────────────────────────────────┘
                               │
                      AUDIT RECORD → logs/audit_log.jsonl → pushed to GitHub
```

**Five places can stop a trade**: the signal guard, the faithfulness guard, the rulebook, the
risk gate, and the reconciliation guard. Only one place can start one.

---

## Why the model is the least trusted component

The interesting failure in an LLM trading agent is not "it picked a bad trade". It is the
model reasoning fluently about a number that was already wrong, or the agent acting on a
position map that no longer matches the broker. The four guards
([`src/guards.py`](../src/guards.py)) are structured on TradeTrap's attack-surface taxonomy
(arXiv:2512.02261):

| Guard | Catches | Blocks |
|---|---|---|
| Signal validation | Out-of-range, NaN, internally inconsistent signals — before any model is called | Yes |
| Faithfulness | The live model quoting a signal value it was never given | Yes |
| Cross-model agreement | The live model as lone dissenter against the shadows | Records only |
| Reconciliation | Position map disagreeing with an independent read of broker state | Yes |
| Circuit breaker | Repeated execution failures; persisted to disk so it survives the restart between cycles | Yes |

**None of them calls a model.** A guard that asked an LLM whether the LLM was lying would
defeat its own purpose.

---

## The shadow benchmark

Three models receive an identical signal vector every cycle. One executes; the other two are
recorded. Because the rulebook is a pure function of the same signals, every answer is
markable right or wrong **immediately** — compliance is measurable today, where profitability
is not measurable for weeks.

Three behaviours are separated, and conflating them is the usual mistake:

- **compliant** — returned the strategy the rulebook mandates
- **abstained** — returned cash when a trade was mandated. Permitted, and not an error: the
  model's discretion is exactly the discretion to decline
- **off-book** — returned some third strategy. This is the failure the gate exists to catch

Scored by [`scripts/model_benchmark.py`](../scripts/model_benchmark.py). Ranking is by
off-book rate, not by compliance rate: ranking on compliance would punish caution and flatter
a model that always proposes something, which is the opposite of what this system values.

---

## Autonomy boundary

**Two independent triggers**, because GitHub's own scheduler proved unreliable — due four
times across Aug 29–Sep 1, fired once, four hours late:

- cron-job.org POSTs `workflow_dispatch` at 13:28 and 19:00 UTC (primary)
- GitHub `schedule:` fires the same two times (backup, supplies its own live-session inputs)

A concurrency group with `cancel-in-progress: false` means that if both fire, the second
queues rather than double-trading. Two independent systems must fail on the same day for a
session to be missed, and neither of them is a person.

**Inside a session, nothing is approved by a human.** The agent decides, sizes, submits,
manages exits and halts itself on drawdown. What stays human is credential custody and the
kill switch.

**The kill switch** ([`src/live_settings.py`](../src/live_settings.py)) has four modes:
`running`, `exit_only`, `flatten`, `paused`. It is fetched from GitHub raw on `main`, so it
can be thrown from a phone. It can only ever make the agent do **less**. Risk limits are not
in it — those live in `config/risk_limits.yaml` and are hand-edited only, because a limit the
running system can change is not a limit.

When settings cannot be read, the agent falls back to `exit_only`, not `running`. That was a
bug once: the kill switch failed **open**.

---

## Execution

Orders go through Alpaca's **CLI** as a subprocess, not the Python SDK. Two reasons: the CLI
is built for long-running agent sessions and cron jobs, and it means the exact command that
reached the broker is a string that can be written into the audit log verbatim.

- **`alpaca doctor` runs out of process before any order is built** and resolves the trading
  host. If it is not `paper-api.alpaca.markets`, the job dies. The agent cannot discover
  after the fact that it was pointed at a live account.
- **`--order-class mleg`** — all legs fill together or none do. There is no state in which
  this agent holds one leg of a spread and unlimited risk on the other side.
- **`client_order_id`** on every submission, so a retry cannot double-fill.
- **Limit orders are cancelled after 20 minutes** and the whole decision re-made from current
  signals. A limit is priced once, at the mid when it is built; a spread whose mid has moved
  cannot fill, and while it rests it counts as claimed exposure and blocks its own underlying
  from being proposed again.

---

## Data and provenance

Every audit record stamps `decision_time` and `data_cutoff`. The agent decides only on data
timestamped at or before the decision instant, and is scored on outcomes that have not
happened yet — so the look-ahead failure described in Look-Ahead-Bench (arXiv:2601.13770),
where a model recites memorised outcomes and backtested alpha evaporates live, is excluded by
construction rather than by assertion. The stamps make that checkable.

`logs/audit_log.jsonl` is the single source of truth. The dashboard is a view over it and
never a second source; it fetches the file from GitHub raw on every request.

---

## Known limits, stated rather than hidden

- **The classifier's bull branch has never fired.** Its label is P(3-day return > +0.5%),
  whose base rate is 0.40–0.49 by underlying, while the rulebook's thresholds (0.44 / 0.56)
  assume 0.50 is neutral. In 203 cycles `p_up` never exceeded 0.531 against a 0.56 threshold,
  so every trade the system has made was bearish or neutral **by construction, not by view**.
  Found by instrumenting our own system; not fixed mid-competition, because changing the
  rulebook would invalidate the accumulated record.
- **IV rank is untrusted for part of the universe.** The trust gate requires 30 samples across
  ≥2 calendar days; IWM and DIA have never satisfied it, so the premium branch stays closed
  for them.
- **A daily model is queried every 15 minutes.** The classifier trains on daily bars, so
  intraday its output is close to constant — SPY produced 5 distinct values across 39 cycles.
- **P&L is not evidence.** Five sessions and a handful of trades cannot support a claim of
  edge in either direction, and this document does not make one.

---

## Repository map

| Path | What it is |
|---|---|
| `src/orchestrator.py` | One cycle, end to end |
| `src/scheduler.py` | Session loop, market clock, exits before entries |
| `src/decision_schema.py` | The rulebook, the system prompt, decision parsing |
| `src/risk_gate.py` | Deterministic sizing and approval. No AI |
| `src/guards.py` | The four integrity guards |
| `src/execution.py` | Spread construction, leg selection, limit pricing |
| `src/alpaca_cli.py` | Every call to the broker, and the paper-endpoint gate |
| `src/positions.py` | Exits, flatten, stale-order cancellation |
| `src/live_settings.py` | Kill switch and remote settings |
| `src/agent_state.py` | Cross-cycle state — breaker, loss streaks, heartbeat |
| `src/signals/` | `direction.py` (LightGBM), `iv_rank.py`, `azte.py` |
| `config/risk_limits.yaml` | Hand-edited only. Never remotely toggleable |
| `dashboard/` | Next.js read-only dashboard |
| `logs/audit_log.jsonl` | The record. Everything else is a view over this |
| `tests/` | 153 tests |
