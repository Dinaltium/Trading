# lablab submission copy — paste-ready

Form is at **0%**, Step 1 of 3, at `/ai-hackathons/alpaca-ai-trading-agents-hackathon/aaf11/submission`.

Replace every `{{NAME}}` before pasting. Character counts below are measured and sit inside
the form's limits with room to spare — re-count if you edit.

---

## Submission Title (5–50 chars)

Pick one, then use the same name everywhere — title, cover image, deck, video, Day 5 post.

| Option | Chars |
|---|---|
| `Brightline — Autonomous Options Agent` | 37 |
| `Nullius — Autonomous Options Agent` | 34 |
| `Recusal — Autonomous Options Agent` | 34 |

The bare name alone also fits and is punchier if the cover image carries the subtitle.

---

## Short Description (50–255 chars)

**Use this one — 219 chars:**

```
An options agent where the language model may decline a trade but can never invent one. A deterministic rulebook picks the strategy, plain Python sizes it, and three models are scored against the same rules every cycle.
```

Alternative, 203 chars, leads on the benchmark:

```
Three AI models see identical signals every 15 minutes and every one is scored against the same deterministic rulebook. The model that executes may decline a trade — it can never propose a different one.
```

---

## Long Description (600–2000 chars, 100 words min)

**1,826 characters, 291 words.** Leads with the benchmark, because that is the part no other entrant has.

```
Three AI models receive an identical vector of measured signals every 15 minutes, and every
one of them is scored against the same deterministic rulebook. Which models follow the rules,
which abstain, and which drift becomes counted evidence in a public audit log rather than a
claim. One model executes; the other two are shadows that never touch the account.

The executing model's authority is deliberately narrow. A rulebook maps every possible
(IV Rank, P(Up)) pair to exactly one strategy. The model may return that strategy or it may
return cash. Anything else is rejected in Python, re-derived from the raw signals rather than
trusted from the model's own summary of them. Discretion to decline, never to substitute.

No model touches arithmetic that moves money. Position size comes from quarter-Kelly on a
calibrated LightGBM probability, never a model's self-reported confidence. Defined-risk
spreads only, max loss capped at 2% of equity per trade, a 5% daily drawdown halt, one
position per underlying, and a premium-selling halt scoped to short-volatility structures.

Four deterministic guards, structured on the TradeTrap taxonomy, assume the agent's own
inputs and outputs can be wrong: signals are validated before any model is consulted, every
figure the model quotes must match what it was handed, cross-model agreement is recorded, and
the position map is reconciled against a second independent read of broker state.

An operator can flatten the entire book in one action and can never choose a single trade.

Orders submit through the Alpaca CLI as atomic multi-leg orders, with the paper endpoint
verified out-of-process before any order is built. Every cycle, every refusal and every defect
we found in our own work is published — including the signal that read 100.0 for four days
while every test passed.
```

---

## Categories / Event Tracks

`Options Alpha Agents`

## Technologies Used

`Alpaca` · `Groq` · `Mistral` · `Featherless` · `Claude Code` · `Vercel` · `GitHub Copilot`

Only list what is genuinely used. Do **not** list Anthropic Claude as a model in the loop —
it is registered and disabled, and the audit log shows three models. Claude Code is honest as
a build tool.

## Social Media Post Links 1–5

1. The Day 1–4 thread on X (posted, @RDinaltium)
2. Day 5 — the naming post
3. Day 6 — the cron that never fired
4. Day 7 — the property test that found a divide-by-zero
5. Prateek's LinkedIn version of the strongest one

---

## Steps 2 and 3 — what still has to exist

| Asset | Format | Status |
|---|---|---|
| Cover image | PNG/JPG, **16:9** | not made |
| Video presentation | **MP4** | not made |
| Slide deck | **PDF** | not made |
| Public GitHub repo | — | done |
| Demo / Application URL | — | done, alpaca-trade-intelli.vercel.app |

The rulebook is explicit that missing these "may result in a lower score or exclusion".
