<!--
Canonical source for the one-page submission write-up. The .docx in this folder is a render
of an Aug 30 version and is now stale in several places (it says four models, and predates
the deterministic fallback, adaptive restriction, session runner and limit cushion).

Regenerate the .docx from this file before submitting. One-page target: keep it to roughly
this length. If something has to go, cut the Alpaca-infrastructure detail before cutting the
risk-gate table — judges can read infra in the repo, but the gate is the claim.

PROJECT NAME: not yet chosen. Replace every {{NAME}} token before submitting.
PAPER ACCOUNT ID: replace {{ACCOUNT_ID}} with the competition account.
-->

**ALPACA AI TRADING AGENTS HACKATHON — OPTIONS ALPHA TRACK**

# {{NAME}}

An autonomous options agent in which a language model may decline a trade but can never
invent one. Every number that moves money is computed by deterministic Python.

**Paper account:** {{ACCOUNT_ID}} · **Repo:** github.com/Dinaltium/Trading · **Dashboard:** alpaca-trade-intelli.vercel.app

---

## AI logic

Every 15 minutes during market hours the agent computes three signals from live Alpaca data:
a **LightGBM directional classifier** P(Up), isotonic-calibrated and walk-forward retrained;
**IV Rank** measured against an accumulating intraday history; and the **Volatility Risk
Premium**, current ATM implied volatility less 20-day realised.

Those signals go to **three models in parallel** — Groq, Featherless and Mistral. Exactly one
is live; the other two run in shadow on identical inputs and never touch the account. Which
one is live is set from a password-gated admin page, so the comparison can be re-pointed
without a redeploy.

The model's authority is deliberately narrow. A **deterministic rulebook** maps every
possible (IV Rank, P(Up)) pair to exactly one strategy. The model may return that strategy,
or it may return cash. It may not return anything else: the same rulebook is re-evaluated in
Python after the model answers, from the raw signals rather than the model's own summary of
them, and any third answer is rejected before sizing. **Discretion to decline, not to
substitute.**

Because all three models are scored against that rulebook every cycle, the audit log
accumulates a like-for-like record of which models follow the rules, which abstain, and which
drift — counted, not asserted.

Two consequences of that design are worth stating, because both were built in response to
things that went wrong rather than anticipated:

- **A model that is unreachable does not stop the agent.** The rulebook is a pure function of
  two measured signals and needs no model to evaluate, so a provider outage executes the
  mandated strategy with no LLM in the loop. This is strictly narrower than what a model is
  allowed to do — it can only ever emit the one strategy a model would have been permitted to
  choose.
- **A signal is only reasoned from once its window can support it.** IV Rank is trusted at 30
  samples across at least two distinct calendar days. An untrusted rank withdraws the
  premium-selling branch and leaves direction, which comes from the classifier and never
  touches the IV window, standing on its own.

## Risk gates

The gate is plain Python with no model call anywhere in it, so a judge can verify it by
reading roughly ninety lines. Position size comes from **quarter-Kelly on the classifier's
calibrated win probability** — never the model's self-reported confidence, which is not a
calibrated probability and is kept for the audit trail only.

| Control | Limit | Enforced by |
|---|---|---|
| Max loss per trade | 2% equity | Kelly sizing capped, then hard-clamped |
| Total open risk | 10% equity | Position shrunk to fit, else rejected |
| Daily drawdown halt | 5% | No new positions for the session |
| Concurrent underlyings | 3 | Distinct-name cap, re-entry exempt |
| Kelly fraction | 0.25 | Quarter-Kelly off calibrated P(win) |
| Premium-selling halt | IV rank 90 | Blocks new short-vol structures only |
| Adaptive restriction | 3 consecutive losses | Bars new entries in that underlying only |

The premium-selling halt is scoped to short-volatility structures rather than applied as a
blanket veto: extreme implied volatility is a reason not to sell premium, not a reason to
stop trading. An earlier blanket reading refused 47 of 47 elevated-volatility cycles,
including 19 textbook iron-condor setups.

Adaptive restriction runs **one way only**. A losing streak on a name is the agent's own
evidence that it is reading that name badly; widening exposure on a winning streak would be
the same reasoning run backwards, and five days of data cannot support it. It is keyed per
underlying, because three losses on one name is evidence about the name while three losses
across three names is evidence about the market. It never restricts exits.

## Integrity guards

Four deterministic checks, structured on the attack-surface taxonomy in **TradeTrap**
(arXiv:2512.02261). None of them calls a model — a guard that asked an LLM whether the LLM
was lying would defeat its own purpose.

**Signal validation** blocks out-of-range, NaN or internally inconsistent signals before any
model is consulted. **Faithfulness** rejects the trade if the live model quotes a signal
figure it was never given. **Cross-validation** records agreement across the independent
models. **Reconciliation** compares the agent's position map against a second, independent
read of broker state and blocks on disagreement.

## Alpaca infrastructure

**Execution via the Alpaca CLI.** Spreads submit as one atomic MLEG order with up to four
legs — all legs fill together or none do, so a partial fill can never leave a naked position.
Each submission is dry-run first, so the logged request body is provably the body that was
sent.

**Out-of-process live-endpoint guard.** `alpaca doctor` runs immediately before every
submission and its resolved Trading endpoint must read `paper-api`. The check runs in a
binary we did not write, against the same profile the order will use, so a mistake in our own
configuration cannot satisfy it.

**Idempotent submission.** Every order carries a generated client order ID, so an ambiguous
failure is resolved by lookup rather than by a blind resubmit.

**Market data and contract selection.** Live option chains supply strikes by delta — short
legs near 0.20, protective wings near 0.10 — rather than hand-assembled OCC symbols. Market
hours come from Alpaca's own clock endpoint, not local timezone arithmetic.

**Unattended operation.** The loop runs on GitHub Actions, not a laptop. One job per market
session drives its own 15-minute cadence and exits at the close, after an earlier schedule of
one cron per cycle was found to have been due roughly 36 times and fired zero.

## Evidence, and its limits

Every cycle writes one JSON record: the signals, every model decision, each model's rulebook
verdict, the risk-gate ruling **with its reason**, the guard verdicts and the fill result. The
file is pushed to a public repository and read live by a read-only dashboard, so any claim in
this document can be checked against the log rather than taken on trust.

`docs/graveyard.md` records every defect this agent had, how each was found, and what now
catches it — including a fix that was written and discarded, and why. Two were found by hand
in the audit log; one was found by a property-based test suite within a minute of first
running, in code that had been passing its own tests.

On look-ahead bias, the agent is immune by construction: it decides only on data timestamped
at or before the decision instant and is scored on outcomes that have not yet happened. Every
record stamps `decision_time` and `data_cutoff` so that is checkable rather than asserted.

**What this evidence does not support:** that the strategy is profitable. A five-session P&L
window is mostly noise. What the record does support is narrower and, we think, more
useful — that every refusal is attributable to a named rule, that no model ever sized a
position, and that where the agent was wrong, the log makes it visible.

*Paper trading only; simulated results do not represent actual trading. This document is not
investment advice.*
