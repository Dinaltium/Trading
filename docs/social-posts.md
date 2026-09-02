# Build-in-Public posts — Alpaca AI Trading Agents Hackathon

Drafts for the Social Engagement extra challenge. Up to **5 links** may be submitted with the
final project submission.

**Split:** Rafan posts on X, Prateek posts on LinkedIn.
**Tags — X:** `@lablabai` `@AlpacaHQ` · **LinkedIn:** lablab.ai, Alpaca.

**The arc.** Days 1–4 carry no project name — they are about what was built and what broke.
Day 5 is the naming post, which earns its place precisely because four days of work came
first: the name explains the design rather than decorating it. Days 6–7 use the name.

Days 1–3 are backfill and are written in past tense so they read honestly as catch-up rather
than pretending to have been posted live. Everything in them is checkable against the commit
history and the public audit log.

**Nothing before Day 5 contains a project name.** Say "the agent" or "our agent". Resist the
urge to slip it in early; the reveal only works if it is actually a reveal.

**Rules for editing these:** every number here is real and verified. If you change a figure,
change it to another real one. The whole value of a build-in-public post about setbacks is
that a judge can open the repo and find the setback.

## Before posting anything to X — check all four

1. **Under 280 characters.** Not on Premium, so this is hard. Six of the eight drafts here were
   originally over, one by 113 characters. Count it, do not eyeball it.
2. **Both handles present** — `@lablabai` and `@AlpacaHQ`. The challenge requires tagging both.
   These cost 20 characters; budget them FIRST and write the post into what remains. One post
   went out without them because they were trimmed to make the copy fit, which is backwards:
   the tags are a requirement and the copy is not.
3. **Attach the image to the post it illustrates**, not automatically to the first one.
4. **No em dashes in threaded replies.** The X composer reordered the lines twice when a
   threaded post began with one. Commas type reliably.

Run this before posting:

```bash
python - <<'PY'
v = """paste the post here"""
print(len(v), '<=280' if len(v)<=280 else 'TOO LONG')
print('tags:', '@lablabai' in v, '@AlpacaHQ' in v)
PY
```

---

## Day 1 — Aug 28 · The constraint that shaped everything  ✅ POSTED

### X (Rafan)

```
Day 1 of @lablabai x @AlpacaHQ options hackathon.

One design rule before any code: the LLM never does the math that moves money.

It reasons in words. A deterministic rulebook maps signals → exactly one strategy.
The model can decline that trade. It can't propose a different one.

Discretion to decline, not to substitute.

#buildinpublic
```

### LinkedIn (Prateek)

```
Day 1 of the Alpaca AI Trading Agents Hackathon (lablab.ai x Alpaca).

We started with a constraint rather than a feature: no language model would be allowed
to do arithmetic that decides how much money moves.

The reasoning is simple. LLMs are good at producing plausible trades and bad at refusing
bad ones. So the model gets a narrow job — read a handful of named, pre-computed numbers
and pick a strategy — while a deterministic rulebook decides what is permissible and
plain Python does every piece of sizing.

The property we wanted: a model may decline a trade the rules mandate, but it can never
propose one they don't. That is enforced in code, re-derived from the raw signals rather
than trusted from the model's own summary of them.

Defined-risk spreads only. Max loss is a property of the structure, not a promise.

#BuildInPublic #AITrading #Alpaca
```

---

## Day 2 — Aug 29 · First real order  ✅ POSTED

### X (Rafan)

```
Day 2. First live order filled.

SPY iron condor, 4 legs, submitted as ONE atomic multi-leg order.
All legs fill together or none do — no partial-fill risk where you're
suddenly holding a naked short.

Credit $1.50. Max profit $150, max loss $250. Known before the order existed.

@lablabai @AlpacaHQ #buildinpublic
```

### LinkedIn (Prateek)

```
Day 2: our agent placed its first real order on Alpaca paper trading.

A SPY iron condor — four option legs, submitted as a single atomic multi-leg order.

That detail matters more than it sounds. If you submit four legs as four orders and two
fill, you are no longer holding a defined-risk spread; you are holding a naked short
position you never chose. Alpaca's MLEG order class means all legs fill together or none
do, so "max loss is capped by construction" stays true during execution and not just on
paper.

Credit received $1.50 per contract. Max profit $150, max loss $250, both known before the
order existed.

We also wired the agent's execution path through Alpaca's official CLI rather than the SDK,
specifically so that `alpaca doctor` verifies the resolved endpoint is paper-api
out-of-process, in a binary we did not write, before any order is built.

#BuildInPublic #AITrading #Alpaca
```

---

## Day 3 — Aug 30 · Four guards that assume the agent is wrong  ✅ POSTED

### X (Rafan)

```
Day 3. Built the integrity layer.

Four deterministic guards, none of which call a model:

1. validate signals before any model sees them
2. every figure the model quotes must match what it was handed
3. record cross-model agreement
4. reconcile our position map vs a SECOND independent broker read

A guard that asked an LLM whether the LLM was lying would defeat itself.

@lablabai @AlpacaHQ
```

### LinkedIn (Prateek)

```
Day 3: the integrity layer.

Most failure modes in an LLM trading agent aren't "the model picked a bad trade." They are
the model reasoning confidently about a number that was already wrong, or the agent acting
on a position map that no longer matches reality.

So we built four guards, structured on the attack-surface taxonomy from the TradeTrap paper
(arXiv:2512.02261). None of them calls a model:

1. Signal validation — out-of-range, NaN or internally inconsistent signals are blocked
   before any model is consulted at all.
2. Faithfulness — every signal figure the live model quotes in its reasoning must match what
   it was actually handed. A fabricated number kills the trade.
3. Cross-validation — how many independent models reached the same answer, recorded.
4. Reconciliation — the agent's position map checked against a second, independent read of
   broker state. Disagreement blocks the order.

A guard that asked an LLM whether the LLM was lying would defeat its own purpose.

#BuildInPublic #AITrading #Alpaca #AISafety
```

---

## Day 4 — Aug 31 · The setback post (the strongest one)  ✅ POSTED

### X (Rafan)

```
Day 4. Found a bug that had been lying to us for four days.

IV Rank read exactly 100.0 on every record since Aug 28.
Arithmetically correct. Completely meaningless.

The window behind it: 14 samples, ALL stamped the same afternoon.

"Highest IV of the few hours we've ever measured" is not
"IV is expensive vs recent history."

@lablabai @AlpacaHQ #buildinpublic
```

### LinkedIn (Prateek)

```
Day 4. The most useful thing we found today was our own bug.

Our agent's IV Rank signal read exactly 100.0 on every audit record for four straight days,
and reported the market regime as HIGH_VOLATILITY on the strength of it. The number was
arithmetically correct. It was also meaningless — the window behind it held 14 samples,
every single one timestamped the same afternoon.

"Today's implied volatility is the highest of the few hours we have ever measured" is not
the same claim as "options are expensive relative to recent history." But it reached three
models, the audit log and our public dashboard as if it were.

Cost: a blanket reading of the volatility halt sent 47 of 47 elevated-volatility cycles to
cash, 19 of them textbook iron-condor setups.

The obvious fix was wrong, which is the part worth sharing. Returning "no value" until the
window was deep enough would have routed every strategy to cash — including the directional
trades whose signal comes from a separate classifier that never touches the IV window. It
would have looked like caution and behaved like an outage.

What we did instead: judge the window's depth separately from the number. A rank is trusted
at 30 samples across at least 2 distinct calendar days. Sample count alone would have passed
the bad window — 14 reads as merely thin, and 200 samples inside one session would read as
plenty. The day spread is what catches it.

No test failed for four days. That is the real lesson.

#BuildInPublic #AITrading #Alpaca
```

---

## Day 5 — Sep 1 · The naming post

Post this only after Days 1–4 are up. It works because four days of building came first: the
name is an argument about the design, not a label applied to it.

Swap `{{NAME}}` and pick the matching tagline from the table at the bottom of this file.

### X (Rafan)

```
Four days in, we finally named it.

We built the thing first on purpose. A name you pick before you know
what you've built is decoration.

Meet {{NAME}}.

{{TAGLINE}}

The model reasons. It never decides.

@lablabai @AlpacaHQ #buildinpublic
```

### LinkedIn (Prateek)

```
Four days into the Alpaca AI Trading Agents Hackathon, our project finally has a name.

We deliberately built first. A name chosen before you know what you have built is
decoration; a name chosen after it is an argument about the design.

Introducing {{NAME}}.

{{TAGLINE}}

That is the whole thesis. Our agent hands a language model a handful of named, pre-computed
numbers and asks for one thing: a strategy. A deterministic rulebook has already decided
which single strategy those numbers permit. The model may return that one, or it may return
cash. Anything else is rejected in Python, re-derived from the raw signals rather than
trusted from the model's own account of them.

The model's discretion is the discretion to decline, never to substitute. Everything that
sizes a position, caps a loss or halts the day is plain Python that no model can reach.

Four days of building taught us what the project actually was. Then we named it.

#BuildInPublic #AITrading #Alpaca
```

---

## Day 6 — Sep 2 · The scheduler that never ran

### X (Rafan)

```
Our trading loop was scheduled every 15 min during market hours.

Due ~36 times across two sessions. Fired ZERO.

The workflow was fine — manual runs passed every time, which is exactly why nobody noticed.

Fix: stop needing 26 crons to land. Need 1.

@lablabai @AlpacaHQ
```

### LinkedIn (Prateek)

```
A failure mode worth naming, because it is invisible by design.

Our trading agent was scheduled to run every 15 minutes during US market hours on GitHub
Actions. Across two trading sessions that schedule was due roughly 36 times.

It fired zero times.

The workflow itself was correct. Both manual runs succeeded — which is precisely why it went
unnoticed. Every time anyone checked it directly, it worked. GitHub deprioritises
short-interval cron schedules under load, and we had bet an entire trading day on 26
separate cron events all landing.

The fix was to stop needing them to. The cadence now lives inside the job: one process starts
at the opening bell, drives its own 15-minute loop, and shuts down cleanly at the close or on
a time budget. The day needs one cron event to land instead of twenty-six.

We also added a heartbeat that records minutes since the previous cycle in every audit
record, so a silent scheduler shows up in the log rather than only in its absence.

If your automation only gets checked by running it manually, you are testing the thing that
was never broken.

#BuildInPublic #DevOps #GitHubActions #AITrading
```

---

## Day 7 — Sep 3 · Letting a generator find what we couldn't

### X (Rafan)

```
Property-based tests on our agent. Found a crash in under a minute.

Kelly sizing divides by the payoff ratio. A spread with zero max profit makes it zero — divide by zero, exception out of the RISK GATE.

Reachable on any debit spread quoted at full width.

@lablabai @AlpacaHQ
```

### LinkedIn (Prateek)

```
We added property-based testing to our trading agent today. It found a real crash on its
first run, in under a minute.

Our position sizing uses the Kelly criterion: f* = (p·b − q) / b, where b is the payoff
ratio, max_profit divided by max_loss. When max_profit is zero, b is zero, and the division
raises an exception — out of the risk gate, taking the entire trading cycle with it.

Is that reachable in production? Yes, easily. A debit spread quoted at the full width between
its strikes has exactly no upside, which a wide bid/ask spread at the market open produces
routinely. A bad quote would have taken down the cycle rather than being declined by it.

No hand-written test had thought to price a spread at zero profit. That is the difference
between example-based tests, which assert the behaviour someone thought to check, and
property-based tests, which assert invariants across inputs nobody thought of.

The property that caught it is simple: whatever the risk gate approves, the amount risked
must be within the configured fraction of equity. Generate ten thousand combinations of
equity, payoff, probability and open risk, and check it holds.

A spread with no upside is not a bet with bad odds. It is not a bet at all.

#BuildInPublic #Testing #AITrading #Alpaca
```

---

## Day 8 — Sep 4 · Publishing the graveyard

### X (Rafan)

```
We published every bug our trading agent had.

- IV Rank pinned at 100 for 4 days
- a cron that never fired
- a guard that blocked on a disagreement it invented (AAP ≠ AAPL)
- a bad quote that could kill the cycle

Plus what's still open.

@lablabai @AlpacaHQ
```

### LinkedIn (Prateek)

```
We published the graveyard: every defect our trading agent had, how each was found, and what
now catches it.

Six entries. Every one was live in code that passed its own test suite.

The one I'd point at: adding a fourth underlying surfaced two different derivations of the
ticker symbol. One part of the agent took the first three characters, giving "AAP" for an
AAPL option contract. Another took the leading run of letters, giving "AAPL". Our
reconciliation guard compares those two sets — so the first AAPL position would have
reconciled as simultaneously missing and phantom, and blocked its own order. A guard failing
on a discrepancy that did not exist. Correct for SPY, QQQ and IWM purely because all three
are three letters long.

Two independent derivations of the same fact is exactly the class of bug that guard exists to
catch, which is a good argument for the fact having one definition.

The document also has a section on what is deliberately still open: our event-trigger is
computed but not enforced, our open-risk figure is a conservative proxy rather than an exact
reconstruction, and five days of P&L is not evidence of edge in either direction.

An autonomous agent that handles money should be judged on what it got wrong and fixed, not
only on what it claims. Stating the limits plainly is worth more than a claim that survives
only until someone reads the code.

#BuildInPublic #AITrading #Alpaca #Engineering
```

---

## Taglines for the naming post

Whichever name is chosen, drop the matching line into `{{TAGLINE}}`.

| Name | Tagline |
|---|---|
| **Brightline** | A bright-line rule admits no judgment. Neither does ours. |
| **Nullius** | *nullius in verba* — take nobody's word for it. Not even the model's. |
| **Recusal** | It can step aside. It cannot rule. |
| **Assay** | Every claim the model makes is tested before it can reach the broker. |
| **Attest** | Every decision, and every refusal, is on the record. |
| **Provenance** | Every decision stamped with what it knew, and when. |
| **Ratchet** | It only ever tightens. |

---

## Notes on picking the five

- **Day 4 (IV Rank)** and **Day 7 (Kelly crash)** are the strongest. Both are concrete,
  checkable, and about being wrong — which is what the challenge actually asked for.
- **Day 6 (cron)** travels furthest outside trading. It's a DevOps story anyone who has
  written a scheduled job recognises.
- Day 1 and Day 2 are context. Post them, but don't expect reach.
- **Day 5 (naming)** is the one to boost if any post gets paid promotion — it is the only
  one that carries the project's identity, and the five links you submit should not all be
  anonymous.
- Don't post rival comparisons. It reads badly and adds nothing.
- Attach the architecture diagram (`docs/architecture.svg`) to at least one LinkedIn post —
  image posts reach further, and it's genuinely good.

---

## Day 5 — the naming post (X)

Ships with a dashboard screenshot. Tag check before posting: **@lablabai @AlpacaHQ**.

```
It has a name now: Brightline.

A bright-line rule is one that admits no judgment — you are over the line or you are not,
and no one gets to argue about it. That is what sits between our model and the broker.

Every 15 minutes three models get an identical signal vector. One of them can reach the
account. The other two are recorded and scored against the same rulebook, so we can mark
every answer right or wrong the same day instead of waiting weeks for P&L to say something.

167 cycles so far. The models tried to go off-book on 6-25% of them, depending which model.
None of those reached the broker.

The model has discretion to decline. It has never had discretion to substitute.

Live, read-only, updates itself: alpaca-trade-intelli.vercel.app

@lablabai @AlpacaHQ #BuildInPublic #AITrading
```

Screenshot to attach: the **Live vs. shadow** section, framed so one cycle card is fully
visible — the four signal values across the top, then Groq / Featherless / Mistral each with
their own strategy and full reasoning, and a red `RISK GATE ✕ rejected` with its stated
reason at the bottom. That single card is the entire thesis in one image: same inputs, three
different answers, one gate, a refusal with a reason attached.

Take it at desktop width. Do not crop the reasoning text — the length is the point.
