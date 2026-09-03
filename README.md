# Brightline

> A bright-line rule admits no judgment. Neither does ours.

An autonomous options-trading agent for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon)
(lablab.ai × Alpaca, Aug 28 – Sep 4 2026), Options Alpha track. Team AAF11.

**Live dashboard** (public, read-only): https://alpaca-trade-intelli.vercel.app
**Alpaca paper account:** `PA3LKGJM8E2F`

| | |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | The system as it actually runs |
| [`docs/graveyard.md`](docs/graveyard.md) | Every defect this agent has had, and what now catches it |
| [`docs/handover.md`](docs/handover.md) | Setup, secrets, how to run it |
| [`docs/architecture.svg`](docs/architecture.svg) | One-page diagram |
| [`docs/playbook.html`](docs/playbook.html) · [`docs/markets101.html`](docs/markets101.html) | Full walkthrough · options basics, no finance background assumed |

---

## The idea in one paragraph

An LLM proposes; deterministic Python disposes. Every 15 minutes the agent builds its own
signals, asks three language models the same question, and lets exactly one of them reach the
broker — behind a rulebook and a risk gate the model cannot argue with. **The model may
decline a trade the rules mandate. It can never propose one they don't.** That is not a
policy the model is asked to follow; it is a property of the code path, because the mandated
strategy is recomputed in Python from the raw signals and compared against whatever the model
said.

## Why three models

Three models receive an identical signal vector every cycle. One executes; the other two are
recorded and scored and never touch the account.

Because the rulebook is a pure function of the same signals, **every answer is markable right
or wrong immediately** — you do not wait weeks for P&L to say something. Compliance is
measurable today; profitability is not. Over the run the models tried to go off-book on
6–25% of cycles depending which model, and **none of those reached the broker**. That is
counted, in a public log, not claimed.

Run [`scripts/model_benchmark.py`](scripts/model_benchmark.py) against `logs/audit_log.jsonl`
to reproduce the scoring.

## The pipeline

```
Every 15 minutes, market hours, per underlying (SPY · QQQ · IWM · DIA):

  1  Live price and option chain from Alpaca
  2  Signals: LightGBM P(Up) (isotonic-calibrated) · IV Rank · VRP · regime
  3  GUARD 1  signal validation — out of range, NaN or inconsistent and no model is called
  4  Three models in parallel:  groq LIVE · featherless shadow · mistral shadow
  5  GUARD 2  faithfulness — a figure quoted but never handed over kills the trade
  6  GUARD 3  cross-model agreement — recorded, does not block
  7  RULEBOOK re-derived in Python from the RAW signals, not the model's summary of them
  8  RISK GATE (zero AI) — quarter-Kelly, ≤2% per trade, ≤10% open risk, drawdown halt,
     one position per underlying, ≤4 concurrent, premium-selling halt, loss-streak restriction
  9  GUARD 4  reconciliation against a second independent read of broker state
 10  Execute: `alpaca doctor` paper check out of process → one atomic MLEG order → client id
 11  One audit record — signals, 3 decisions, 4 guard verdicts, rulebook ruling, gate verdict,
     fill — appended to logs/audit_log.jsonl and pushed to GitHub
 12  Dashboard reads that file fresh on every request
```

Five stages can stop a trade. One can start one.

## Autonomy

Nothing inside a session is approved by a human. The agent decides, sizes, submits, manages
its own exits, and halts itself on drawdown.

**Two independent triggers**, because GitHub's scheduler proved unreliable — due four times
across Aug 29 – Sep 1, fired once, four hours late. cron-job.org is primary; GitHub `schedule:`
is the backup and supplies its own live-session inputs. A concurrency group means that if both
fire, the second queues rather than double-trading. Two independent systems have to fail on
the same day for a session to be missed, and neither of them is a person.

**The kill switch** is the only write the dashboard exposes. Four modes — `running`,
`exit_only`, `flatten`, `paused` — fetched from GitHub raw so it can be thrown from a phone.
It can only ever make the agent do less. Risk limits are deliberately **not** in it: they live
in `config/risk_limits.yaml`, hand-edited only, because a limit the running system can change
is not a limit.

## Execution

Orders go through Alpaca's **CLI** as a subprocess rather than the SDK — it is built for
long-running agent sessions and cron jobs, and it means the exact command that reached the
broker is a string in the audit log, verbatim:

```
alpaca order submit --order-class mleg --qty 14 --type limit --limit-price 1.42 \
  --legs [{"symbol":"DIA260911P00530000","side":"buy",...},{...}] --client-order-id oaa-…
```

- `alpaca doctor` resolves the trading host **out of process** before any order is built. Not
  `paper-api.alpaca.markets`, the job dies.
- `mleg` — all legs fill together or none do. There is no state where this agent holds half a
  spread and unlimited risk on the other side.
- Resting limits are cancelled after 20 minutes and the decision re-made from current signals.

### CLI and SDK — which does what, and why

Alpaca's FAQ asks that any SDK use be explained. Both are used here, and the split is
deliberate:

| | Used for | Why |
|---|---|---|
| **Alpaca CLI** | **Every order.** Submit, cancel, position and order reads, and the paper-endpoint check | Orders are the part that moves money. The CLI is built for long-running agent sessions and cron jobs, and it makes the exact submitted command a string in the audit log — an SDK call is not quotable that way |
| **`alpaca-py`** (official SDK) | Market data only: option chains, stock bars, the market clock, and account equity reads | Historical bars and option-chain snapshots are a data problem, not an execution one. The classifier needs 900 days of bars per cycle, which is a data-client job |

The rule the codebase holds to: **nothing that changes the account goes through the SDK.**
`src/alpaca_cli.py` is the only module that submits or cancels anything, and it shells out to
the CLI every time.

## The integrity layer

Four deterministic guards ([`src/guards.py`](src/guards.py)), structured on
[TradeTrap](https://arxiv.org/abs/2512.02261)'s attack-surface taxonomy. **None of them calls
a model** — a guard that asked an LLM whether the LLM was lying would defeat its own purpose.

| Guard | Catches | Blocks |
|---|---|---|
| Signal validation | Out-of-range, NaN, inconsistent signals, before any model is consulted | Yes |
| Faithfulness | The live model quoting a signal value it was never given | Yes |
| Cross-model agreement | The live model as lone dissenter against the shadows | Records |
| Reconciliation | Position map disagreeing with an independent read of broker state | Yes |
| Circuit breaker | Repeated execution failures, persisted to disk so it survives cycle restarts | Yes |

### On look-ahead bias

[Look-Ahead-Bench](https://arxiv.org/abs/2601.13770) shows an LLM scored on historical data may
be reciting memorised outcomes rather than predicting, producing backtested alpha that
evaporates live. **This agent is immune by construction**: it decides only on data timestamped
at or before the decision instant and is scored on outcomes that have not happened yet. Every
record stamps `decision_time` and `data_cutoff`, so the claim is checkable rather than asserted.

### Research this implements

| Paper | What we took |
|---|---|
| [TradeTrap](https://arxiv.org/abs/2512.02261) | The four-component attack-surface taxonomy — the structure of `src/guards.py` |
| [AgenticAITA](https://arxiv.org/abs/2605.12532) | Deterministic safety constraints bounding agent behaviour independently of LLM stochasticity; AZTE selective activation |
| [Look-Ahead-Bench](https://arxiv.org/abs/2601.13770) | Temporal provenance stamping, forward-only live evaluation |
| [The Alpha Illusion](https://arxiv.org/abs/2605.16895) | Validity protocols P1–P6 — counterfactual probing and multi-agent disaggregation, in `scripts/` |
| [Agent Market Arena](https://arxiv.org/abs/2510.11695) | Framework variation dominates backbone variation — the shadow benchmark measures the residual |

PDFs are not redistributed here; they are the authors' work. Follow the links.

## The dashboard

Read-only by construction. It cannot place, modify or cancel an order.

- **Where it stands** — a plain-language account of the account, computed from the audit log.
  Deliberately not model-written, and the panel says so.
- **Ask the model to explain this** — a Featherless model reads the *computed figures* and
  explains them. It never sees the raw log and never does arithmetic, and **every number in
  its reply is checked against the record before the reply is shown**. A briefing that states
  an untraceable figure is rejected and never rendered. Same shape as the risk gate: the model
  proposes, something deterministic decides.
- **Agent activity** — the running feed of cycles, decisions, verdicts and fills, with the
  gate's stated reason attached to every refusal.
- **Live vs. shadow** — all three models' full reasoning, never truncated.

## Status

- [x] Deterministic rulebook, risk gate, four guards, circuit breaker
- [x] LightGBM direction signal — calibrated, retrained every cycle, multi-symbol backtested
- [x] Atomic MLEG execution via the Alpaca CLI, paper endpoint re-verified out of process
- [x] Position management — stop-loss, take-profit, flatten, stale-order cancellation
- [x] Operator kill switch, four modes, password-gated, cannot raise risk
- [x] Two independent schedulers; no human needed to start a session
- [x] Public read-only dashboard with live activity feed and verified model briefing
- [x] 203 cycles logged across Aug 30 – Sep 2, every one auditable
- [x] 153 tests
- [ ] Full model-benchmark write-up — run at the close of the measurement window

## Known limits

Stated here rather than left to be found. Detail in
[`docs/architecture.md`](docs/architecture.md) and [`docs/graveyard.md`](docs/graveyard.md).

- **The classifier's bull branch has never fired.** Its label is P(3-day return > +0.5%), whose
  base rate is 0.40–0.49 by underlying, while the rulebook's thresholds assume 0.50 is neutral.
  Every trade this system has made was bearish or neutral **by construction, not by view**.
  Found by instrumenting our own system, and deliberately not patched mid-competition.
- **IV rank is untrusted for part of the universe** — the trust gate needs 30 samples across
  ≥2 calendar days, and IWM and DIA have never satisfied it.
- **A daily model is queried every 15 minutes**, so intraday its output is near-constant.
- **P&L is not evidence.** Five sessions and a handful of trades cannot support a claim of edge
  in either direction, and nothing here makes one.

## Provenance

Everything in this repository was written during the hackathon window (Aug 28 – Sep 4 2026).
The trading session trigger is external — cron-job.org and GitHub's scheduler — and on Sep 2 a
credential rotation required one manual re-dispatch after the automated trigger's run failed at
CLI login. No trade was ever chosen, sized, approved or cancelled by a human.
