# The graveyard

Defects this agent had, how they were found, and what now catches them.

Every entry here was live in code that passed its own test suite. That is the point: each
one is a case where the tests asserted the behaviour someone thought to check, and the bug
lived in the space nobody thought about. They are recorded because an agent that trades
money should be judged on what it got wrong and fixed, not only on what it claims.

---

## 1. `iv_rank` pinned at exactly 100.0 for four days

**What happened.** Every audit record from Aug 28 to Aug 31 carried `iv_rank: 100.0` and
`market_regime: HIGH_VOLATILITY`. The number was arithmetically correct. It was also
meaningless: the window behind it held 14 samples, every one stamped `2026-08-28`. The rank
was saying "today's IV is the highest of the few hours we have ever measured", and it
reached three models, the audit log and the public dashboard as a claim about the market.

**Cost.** A blanket reading of the regime halt sent 47 of 47 elevated-volatility cycles to
cash, 19 of them textbook iron-condor setups.

**How it was found.** By hand, reading the audit log and noticing a number that never moved.
No test failed. The signal guard *warned* — `iv_rank is exactly 100.0 — check the ranking
window is not degenerate` — and a warning nobody reads is not a control.

**The wrong fix.** Return `None` until the window is deep enough. This was written, then
discarded: `rulebook_strategy()` maps a null `iv_rank` to cash, so it would have stopped the
agent taking *any* trade, including the directional ones whose signal comes from the
classifier and never touches the IV window. It would have looked like caution and behaved
like an outage.

**What now catches it.** Depth is judged separately from the number. `history_depth()` counts
samples *and* distinct calendar days; a rank is trusted at 30 samples across 2 days. Sample
depth alone would have passed the bad window — 14 reads as merely thin, and 200 samples
inside one session would read as plenty. **The day spread is what catches it.** An untrusted
rank withdraws the premium branch only; direction still stands.

---

## 2. A scheduled workflow that never once fired

**What happened.** The trading loop was scheduled `*/15 13-20 * * 1-5` and was due roughly 36
times across Aug 29 and Aug 31. It fired **zero** times. Every cycle in the audit log had
been triggered by hand.

**How it was found.** `gh run list` showed two runs, both `workflow_dispatch`. The workflow
itself was correct and both manual runs succeeded, which is exactly why it went unnoticed —
the thing looked healthy every time anyone looked at it directly.

**Cause.** GitHub deprioritises short-interval schedules under load. Betting a trading day on
26 separate cron events landing is a bet with no fallback.

**What now catches it.** The cadence moved inside the job. `src.scheduler --session` drives
its own 15-minute loop and exits at the close or on a budget, so the day needs **one** cron to
land rather than 26. Two fire daily instead of twenty-six. A heartbeat guard also records
minutes since the previous cycle in every record, so a silent scheduler is visible in the
log rather than only in its absence.

---

## 3. Four models advertised, three answering

**What happened.** The write-up claimed four models scored against the rulebook every cycle.
In CI, `claude_code_cli` failed on every unattended record with `'claude' CLI not found on
PATH` — it shells out to a binary that exists on a laptop and not on a GitHub runner. Three
models answered. The audit log was honest; the prose was not.

**The attempted fix that also failed.** Reaching Claude over HTTP instead. The key
authenticated and the workspace resolved, and then every call returned
`400 credit balance is too low` — the organisation's promotional credits are not spendable on
the API. Two providers, two different reasons, same outcome.

**What now catches it.** Both names are out of the set the cycle iterates, so neither burns
part of the 90-second budget on a call that cannot succeed. Both stay registered and tested,
so re-enabling either is one name in a list. **The claim is now three, and three is what the
log shows.**

---

## 4. A guard that would have blocked on a disagreement it invented

**What happened.** Adding AAPL to the universe surfaced two independent derivations of the
underlying ticker. The orchestrator took `symbol[:3]`, giving `AAP` for
`AAPL260904C00320000`. The broker-state read took the leading alphabetic run, giving `AAPL`.
Guard 4 compares those two sets.

**Cost, had it shipped.** The first AAPL position would have reconciled as simultaneously
missing *and* phantom, and blocked its own order — a guard failing on a discrepancy that did
not exist. Correct for SPY, QQQ and IWM by luck, because all three are three letters long.

**How it was found.** By tracing what the wider universe would touch before enabling it.

**What now catches it.** One definition, `alpaca_cli.underlying_root()`, called by both
sides. Two independent derivations of the same fact is precisely the class of bug Guard 4
exists to catch, which is a good argument for the fact having a single definition.

---

## 5. A bad quote could kill the whole cycle

**What happened.** `_kelly_fraction()` computes `f* = (p·b − q) / b` where `b` is the payoff
ratio `max_profit / max_loss`. When `max_profit` is zero, so is `b`, and the division raises
`ZeroDivisionError` out of the risk gate and takes the cycle with it.

**Reachability.** A debit spread quoted at the full width between its strikes has exactly no
upside. A wide bid/ask at the open produces that easily. A bad quote would take down the
tick rather than being declined by it.

**How it was found.** The property-based suite, on its first run, in under a minute. No
hand-written case had thought to price a spread at zero profit.

**What now catches it.** `b <= 0` returns zero. A spread with no upside is not a bet with bad
odds; it is not a bet at all.

---

## 6. Regime config that nothing read

**What happened.** The `market_regime_gate` block in `risk_limits.yaml` was dead config until
Aug 30. Nothing loaded it. The only volatility halt in the system was a sentence in the LLM
prompt asking the model nicely — making it the one risk rule with no deterministic backing,
in a system whose entire claim is that risk decisions never depend on a model.

**What now catches it.** The block is read and enforced in `risk_gate.evaluate()`. Its scope
is deliberately narrow: the halt applies to `iron_condor` (net credit, short volatility) and
not to debit spreads, which are long premium and unaffected by the concern. The previous
blanket reading is what produced the 47-of-47 refusals in entry 1.

---

## What is deliberately still open

**AZTE is computed and logged, but does not gate.** Enforcing the `|z| ≥ 2.0` trigger would
suppress cycles, and a suppressed cycle is a missing benchmark datapoint in a competition
measured in days. The log records what it *would* have suppressed, which is the honest way to
evaluate a gate before trusting it.

**The open-risk figure is a proxy.** `open_risk_dollars` sums `|market_value|` across option
positions rather than reconstructing max loss per spread from strikes. It is conservative in
the common case and is not claimed to be exact.

**Five days of P&L is not evidence of edge.** Nothing here should be read as a demonstration
that the strategy is profitable. What the record supports is narrower: that the agent decided
only on data timestamped at or before each decision, that every refusal is attributable to a
named rule, and that when it was wrong it was wrong in a way the log makes visible.
