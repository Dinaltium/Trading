# Pitch deck + video script

Two mandatory assets: **slide deck as PDF**, **video as MP4**. Neither exists yet.

Replace `{{NAME}}` throughout. Everything here is checkable against the repo and the public
audit log — if you change a number, change it to another real one.

**Ordering principle:** lead with the three-model benchmark, not the guards. Five entrants in
this track pitch "LLM proposes, deterministic layer disposes" — it's the consensus
architecture here, and a judge will have read it twice before reaching you. Scoring three
models against one rulebook every cycle is the part nobody else does, so it goes first.

---

# Deck — 10 slides

### 1 — Title

> **{{NAME}}**
> An options agent where the model may decline a trade and can never invent one.
>
> Alpaca AI Trading Agents Hackathon · Options Alpha Agents
> Rafan Ahamad Sheik · Prateek D Shriyan · Team AAF11

Use the 16:9 cover image here.

### 2 — The problem, stated as a property

> Ask a language model for a trade and it gives you one. It sounds reasoned, it cites the
> Greeks, and nothing checks whether the numbers it reported match the market.
>
> The agent reports its own inputs, sizes its own positions, and judges its own output.
> **It controls every gate meant to constrain it.**

### 3 — What we built instead *(the originality slide — do not bury it)*

> **Three models. One rulebook. Every cycle. Scored.**
>
> Groq, Featherless and Mistral receive an identical signal vector every 15 minutes.
> One executes. Two shadow. All three are scored against the same deterministic rulebook.
>
> "Which model follows the rules and which drifts" becomes **counted evidence in a public
> audit log** — not a claim.

Show a real audit record here. The 16:53 SPY cycle is ideal: Groq and Featherless both chose
`bear_put_spread`, Mistral chose `cash`. Genuine disagreement, logged.

### 4 — The rulebook

> A deterministic function maps every (IV Rank, P(Up)) pair to **exactly one** strategy.
>
> The model may return that strategy. It may return cash. **Nothing else survives.**
>
> The same rulebook is re-derived in Python *after* the model answers — from the raw
> signals, not from the model's summary of them.
>
> **Discretion to decline, never to substitute.**

### 5 — No model touches the arithmetic

| Control | Limit |
|---|---|
| Max loss per trade | 2% of equity |
| Total open risk | 10% |
| Daily drawdown halt | 5% |
| Position sizing | quarter-Kelly on a **calibrated** LightGBM probability |
| Concurrency | one position per underlying |
| Premium-selling halt | IV rank ≥ 90, short-vol structures only |

> Never the model's self-reported confidence. An LLM confidence score is not a calibrated
> probability, and feeding one into Kelly is the exact hallucination risk the gate exists
> to prevent.

### 6 — Four guards that assume the agent is wrong

Structured on the TradeTrap taxonomy (arXiv:2512.02261). **None of them calls a model.**

> 1. Signals validated **before any model is consulted**
> 2. Every figure the model quotes must match what it was handed
> 3. Cross-model agreement, recorded
> 4. Position map reconciled against a **second independent broker read**
>
> A guard that asked an LLM whether the LLM was lying would defeat its own purpose.

### 7 — The autonomy boundary *(this is the Prateek slide)*

> **One action flattens the entire book. No action selects a trade.**
>
> Running · Exit only · Flatten · Paused
>
> The operator can stop everything, instantly, for any reason. The operator can never choose
> what to buy.
>
> Contrast: an agent that stops and asks a human before every order has answered the safety
> question by giving up the autonomy this track asks for.

### 8 — Alpaca implementation

> - Orders through the **Alpaca CLI**, atomic multi-leg (MLEG) — all legs fill or none do,
>   so a partial fill can never leave a naked short
> - `alpaca doctor` verifies the resolved endpoint reads `paper-api` **out-of-process**,
>   in a binary we did not write, before any order is built
> - Idempotent submission — every order carries a generated client order ID
> - Strikes selected by delta from live chains; market hours from Alpaca's own clock
> - Unattended on GitHub Actions, one session per trading day

### 9 — The graveyard *(the credibility slide)*

> Every defect this agent had is published, with how it was found and what now catches it.
>
> - **IV Rank read exactly 100.0 for four days.** 14 samples, all one afternoon. Sent 47 of
>   47 cycles to cash. No test failed.
> - **A scheduled workflow due ~36 times fired zero times** — and later fired 4 hours late,
>   green, after the close.
> - **A guard that would have blocked on a disagreement it invented** — `AAP` vs `AAPL`.
> - **A property test found a divide-by-zero in the risk gate** in under a minute, in code
>   that was passing its own suite.
>
> Including a fix we wrote and threw away, and why.

### 10 — What the evidence does and does not support

> **Does:** every refusal is attributable to a named rule. No model ever sized a position.
> Decisions used only data timestamped at or before the decision instant — stamped per record.
>
> **Does not:** that the strategy is profitable. A five-session P&L window is mostly noise,
> for us and for everyone else in this track.
>
> Live: `alpaca-trade-intelli.vercel.app` · Repo: `github.com/Dinaltium/Trading`

---

# Video script — ~2:30

Format agreed in the Aug 30 meeting: interactive explainer, on-screen subtitles, phones for
audio. Screen-record the real dashboard and the real Actions tab — **do not mock anything.**

**[0:00–0:20] Cold open — the problem**

> "If you ask a language model for a trade, it will give you one. It'll sound reasoned. It'll
> cite the Greeks. And nothing anywhere checks whether the numbers it just quoted match the
> actual market.
> We built an options agent on the opposite assumption: that the model is the least
> trustworthy component in the system."

**[0:20–0:50] The differentiator — screen: audit log**

> "Every fifteen minutes, three AI models get an identical set of measured signals. One of
> them executes. The other two shadow it. And all three are scored against the same
> deterministic rulebook, every single cycle.
> So 'which model follows the rules and which one drifts' isn't an opinion we hold — it's
> counted, in a public log. Here's a real cycle: two models agreed on a bear put spread,
> the third declined entirely."

**[0:50–1:20] The constraint — screen: `decision_schema.py`**

> "The rulebook maps every combination of signals to exactly one permitted strategy. The
> model can return that strategy, or it can return cash. Anything else is rejected — in
> Python, re-derived from the raw signals rather than trusted from the model's own summary.
> Discretion to decline. Never to substitute."

**[1:20–1:45] Risk — screen: `risk_gate.py`**

> "No model touches the arithmetic that moves money. Sizing is quarter-Kelly on a calibrated
> classifier probability — never the model's self-reported confidence, because that isn't a
> calibrated probability and feeding it into Kelly is exactly the failure we're guarding
> against. Two percent max loss per trade. Five percent daily drawdown halt. Defined-risk
> spreads only, so max loss is a property of the structure."

**[1:45–2:05] The operator boundary — screen: `/admin`**

> "It runs unattended. But a human can flatten the entire book in one action — close every
> position, cancel every resting order, stop.
> What a human can never do is pick a trade. One action stops everything; no action selects
> anything. That's the line that keeps it autonomous instead of human-driven."

**[2:05–2:30] The graveyard — close**

> "We also published every bug this agent had. A volatility signal that read exactly 100 for
> four days while every test passed. A scheduled job that was due thirty-six times and fired
> zero. A guard that would have blocked on a disagreement it invented.
> Five sessions of P&L is mostly noise — for us and for everyone else here. What the record
> does show is that every refusal traces to a named rule, and that when we were wrong, the
> log makes it visible."

---

# Cover image — 16:9, PNG or JPG

Keep it typographic; screenshots don't read at thumbnail size.

> **{{NAME}}**
> *The model may decline a trade. It can never invent one.*

Dark background, monospace, the project name large and the line beneath it small. Add the
Alpaca and lablab.ai marks if you have clean assets. One idea, legible at 200px wide.

---

# Recording checklist

- [ ] Real dashboard, real Actions tab, real audit log — nothing mocked
- [ ] Subtitles burned in (agreed Aug 30)
- [ ] Phone audio, not laptop mic
- [ ] **Blur or crop the API key panel** on the Alpaca dashboard before recording
- [ ] Export MP4, deck as PDF, cover 16:9
- [ ] Say "three models" — not four. The audit log shows three.
