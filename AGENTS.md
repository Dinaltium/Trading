# AGENTS.md — Alpaca AI Trading Agents Hackathon

Guidance file for Claude Code (and any other agent) working in this repo. Read this first, every session.

**Team:** Rafan (CTO, AAF11) + Prateek (COO, AAF11)
**Event:** Alpaca AI Trading Agents Hackathon (lablab.ai), kickoff **today 8:30pm**
**Track:** Options Alpha Agents
**Window:** Aug 28 – Sep 4, 2026. Submit by Sep 4, 15:00 UTC. ~5 US trading days inside window.
**Hackathon page:** https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon

---

## 1. Objective

Autonomous AI agent trading **options** on Alpaca paper trading. Judged on risk-adjusted return, not raw P&L. Discipline + explainability > size.

---

## 2. Hard Requirements

- Final submission runs on a **brand-new, dedicated paper account** — not the dev account. Create fresh account right before final run.
- Competition account starting balance: exactly **$100,000**.
- Deliverable: **one-page write-up** — AI logic, risk gates, Alpaca infra.
- Hackathon may drop **additional files/instructions later tonight at kickoff** — check repo root, user will add them here.

---

## 3. Prizes & Payee (context only, not build-relevant)

| Place | Amount |
|---|---|
| 1st | $2,500 |
| 2nd | $1,500 |
| 3rd | $1,000 |
| Social Engagement (2 teams) | $500/team + 1mo Algo Trader Plus each |

- **Rafan is designated payee** if we win.
- Non-US payee needs W-8BEN + gov ID + bank details within 90 days.
- Don't assume India-US tax treaty reduces the standard 30% withholding — verify with a CA later, not a build blocker.
- Unconfirmed: does the $500 social prize need 1 poster or whole team? Check Discord at kickoff.

---

## 4. Judging Criteria

1. **P&L Performance** — actual paper trading result.
2. **Technology Implementation** — real use of Alpaca Trading API / MCP server / CLI, not a pipeline dressed up as an agent.
3. **Creativity & Originality** — strategy + agent behavior.
4. **Presentation & Execution** — demo clarity, trade reasoning shown.

Favor **short-dated (weekly) options** on liquid names (SPY, QQQ, or 1-2 liquid single names) — only ~5 trading days to show movement.

---

## 5. Architecture

### Our loop (core, build this first)

```
Scheduler (every ~15 min, market hours)
        │
        ▼
LLM agent (Claude) ◄──── tool calls ────► Alpaca MCP server
  reads state,                              market data + account tools
  proposes trade
        │
        ▼
Risk gate (hard-coded, NOT an LLM call)
  checks max loss / drawdown limits
        │
   ┌────┴────┐
   ▼         ▼
Alpaca      Order
paper       rejected,
account     logged
(multi-leg
order)
   │         │
   └────┬────┘
        ▼
   Audit log (reasoning + trade history)
        │
        ▼
   ↻ loop back to scheduler
```

- **Risk gate is hard-coded middleware**, not a prompt instruction — intercepts the LLM's proposed order, forwards to Alpaca only if it passes explicit rules. Makes "risk gates" verifiable to judges, not just claimed.
- **`alpaca-py` SDK, wrapped as Groq/Claude tool-call functions, is the LLM's interface to Alpaca** — this is the "Technology Implementation" story: genuine tool orchestration (`get_option_chain`, `get_option_snapshot`, `place_option_order`), not a hand-coded pipeline. (Revised from "MCP server only" — the `alpaca-trading-paper-trading-mcp` skill itself recommends SDK-direct for unattended/standalone automation; MCP kept available for interactive dev-time testing only. Satisfies hackathon's "MCP or CLI" requirement via the CLI/SDK path. Full reasoning: `BRAINSTORM.md` §7d.)
- Every cycle (passed or rejected) writes to the **audit log** — source material for the write-up and demo.

### Reference pattern (from Alpaca's own multi-agent article — stretch goal, borrow ideas not the whole thing)

Source: https://alpaca.markets/learn/building-a-multi-agent-ai-trading-system-on-alpaca

```
Alpaca OHLCV + Finnhub + yfinance + FRED
    ↓
Regime-aware screener
    ↓
N research agents, PARALLEL, ISOLATED (no cross-visibility before proposal)
    ↓
Critic agent → structured investment memo, validated vs governance rules
    ↓
Human gate (APPROVE / REJECT / REVISE)
    ↓
Risk guard (deterministic Python, no LLM)
    ↓
Alpaca execution → position monitor (checks every 15 min, rebuilds missing brackets)
```

Ideas worth stealing if time allows:
- **Isolated parallel agents per strategic lens** (e.g. momentum vs mean-reversion vs macro) prevents signal dilution — could map to different options strategies (bull call spread agent vs iron condor agent vs earnings-vol agent) instead of raw stock strategies.
- **Deterministic `risk_guard.py`** module, run standalone before every order — exactly our risk gate, same philosophy: no LLM in the loop for risk math.
- **OCO bracket orders** (take-profit + stop-loss, GTC) for every entry — reduces need for constant polling to manage exits.
- **Standardized proposal schema** (ticker, direction, thesis, entry conditions, exit params, confidence score) — good shape for our LLM's structured output too.
- No MCP usage in their article — we're ahead on "Technology Implementation" criterion by using MCP directly.
- No framework (LangGraph etc.) mentioned there — plain Python async is enough; don't over-engineer with a framework this week.

Do NOT attempt full 5-agent parallel system as v1. Get the single-loop version working end-to-end first (§11 build plan). Multi-agent lens split is a stretch goal only after core loop is solid and stable.

---

## 6. Strategy

- **Defined-risk options spreads only** — bull call spreads, bear put spreads, iron condors. Never naked long/short.
  - Caps max loss by construction — real risk gate, not a claim.
  - Cheaper entry than naked → can run several concurrent positions in $100k instead of one big bet.
- **Signal blend feeding the LLM's decision:**
  - IV rank / IV percentile (from Alpaca option snapshot data)
  - Technical/momentum indicators (`pandas-ta`)
  - News sentiment (FinBERT)
- Frame objective as risk-adjusted return under hard limits, not raw P&L max — satisfies required "risk gates" write-up section, stronger under Creativity + Tech Implementation criteria.

### Risk gates (hard-coded, non-negotiable)
- Defined-risk instruments only, no naked shorts
- Max loss per trade ≤ 2% of account
- Max total open risk at any time ≤ 10% of account
- Daily drawdown circuit breaker — stop trading for the day past a set loss threshold
- Diversify across 2-3 underlyings, not all-in on one name
- Consider OCO bracket exits (take-profit/stop-loss, GTC) per the reference pattern above, to reduce reliance on the scheduler catching every exit

---

## 6b. Reasoning Engine Plan (Groq → Claude Code, deliberate comparison)

Anthropic API costs money, no meaningful free tier. Decided plan instead of "just use Claude API":

1. **Groq (primary, build against first).** Free, fast, hosted open-source models (Llama etc). Build and validate the whole loop here — structured trade proposals, MCP tool orchestration, risk gate integration — before spending anything on Claude.
2. **Claude Code CLI headless mode (secondary).** Once the Groq loop is solid, swap the reasoning engine to Claude Code (`claude -p ...`, scripted from the scheduler) — reuses existing paid subscription, no separate API billing. Run the same loop, compare behavior/decision quality against Groq.
3. **Local GPU model, 4-10B params (optional stretch).** e.g. `Qwen2.5-7B-Instruct` or `Llama-3.1-8B-Instruct` via Ollama. Only pursue if both above are working and time remains — small local models are weaker at structured JSON + multi-step tool-calling, and GPU/quantization setup costs time. Don't let it block core loop.

Why this order: de-risks the core loop (scheduler, MCP calls, risk gate, audit log) against a zero-cost model first. By the time Claude enters, plumbing is proven — Claude's turn is a reasoning-quality swap, not a rebuild. Also gives a genuine open-source-vs-paid-model comparison to document — stronger "Creativity" and "Technology Implementation" story than just calling one API.

Full reasoning + decisions behind this: see `BRAINSTORM.md`.

---

## 7. Tech Stack

**Language: Python.** `alpaca-py` is the mature SDK for options (Greeks, multi-leg). Agent/quant ecosystem (LangChain/LangGraph, numpy, pandas, py_vollib) is Python-first.

| Component | Tool | Notes |
|---|---|---|
| Reasoning agent | **Groq (free, primary)** → **Claude Code CLI headless (secondary, for comparison)** → local 4-10B GPU model (optional stretch) | See §5b below — deliberate cost/quality comparison, not just budget constraint |
| Alpaca interface | Alpaca MCP server (`uvx alpaca-mcp-server`) | 65 tools incl. `place_option_order`, `get_option_chain`, `get_option_snapshot`, `get_account_info` |
| Trading SDK | `alpaca-py` | Primary Python SDK |
| News sentiment | FinBERT (`ProsusAI/finbert` via `transformers`) | Pretrained, drop-in |
| Technical indicators | `pandas-ta-classic` (PyPI `pandas-ta` is dead/unmaintained; use the classic fork — imports as `pandas_ta_classic`, not `pandas_ta`) | RSI, moving averages, etc. |
| Greeks / IV | Alpaca option snapshot data | Already computed, don't calc manually |
| Backtesting | `alpaca-skills` repo, `alpaca-trading-backtest` skill | Validate strategy before going live |

### On ML: do NOT train a model from scratch
- ~5 trading days is not enough to train/validate/trust a custom model.
- Judges score Tech Implementation on Alpaca stack usage, not homemade models.
- Use pretrained off-the-shelf only (Claude + FinBERT) + deterministic math (IV rank, technicals).
- Optional stretch (only after core loop works, not on critical path): small transparent classifier (logistic regression / XGBoost) trained same-day on a narrow task (e.g. IV expansion vs contraction next day) using Alpaca historical bars.

---

## 8. Repo Structure (target)

```
Trading/
├── AGENTS.md              # this file
├── README.md               # (superseded by this file — keep or merge, see note)
├── LINKS.md                 # raw reference links
├── src/
│   ├── scheduler.py         # market-hours loop, ~15 min cadence
│   ├── agent.py              # Claude reasoning loop, MCP tool calls
│   ├── risk_gate.py           # hard-coded risk rules, no LLM
│   ├── signals/
│   │   ├── iv_rank.py
│   │   ├── technicals.py       # pandas-ta wrappers
│   │   └── sentiment.py         # FinBERT wrapper
│   ├── execution.py           # place_option_order wrapper, logging
│   └── audit_log.py            # reasoning + trade history writer
├── backtests/                 # alpaca-skills backtest usage
├── config/
│   └── risk_limits.yaml        # % caps, drawdown thresholds
├── logs/                        # audit log output (gitignore if it gets big)
└── writeup/                      # one-pager + demo assets
```

Not prescriptive — adjust as build progresses, but keep risk_gate.py and audit logging as separate, clearly isolated modules. Judges (and this write-up) need to point at them directly.

---

## 9. Reference Links

- Hackathon page: https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon
- Getting Started: https://docs.alpaca.markets/us/docs/getting-started
- Trading API: https://docs.alpaca.markets/us/docs/getting-started-with-trading-api
- Market Data API: https://docs.alpaca.markets/us/docs/getting-started-with-alpaca-market-data
- Options Level 3 Trading (multi-leg orders): https://docs.alpaca.markets/us/docs/options-level-3-trading
- Alpaca MCP Server docs: https://docs.alpaca.markets/us/docs/alpaca-mcp-server
- Alpaca CLI: https://github.com/alpacahq/cli / docs: https://docs.alpaca.markets/us/docs/alpacas-cli
- `alpaca-py` (Python SDK): https://github.com/alpacahq/alpaca-py
- `alpaca-trade-api-js` (JS SDK, not our stack): https://github.com/alpacahq/alpaca-trade-api-js
- `alpaca-skills` (backtest + other AI-assisted dev skills): https://github.com/alpacahq/alpaca-skills
- SDKs & OpenAPI Specs: https://docs.alpaca.markets/us/docs/sdks-and-tools
- Multi-Agent reference architecture (ideas source, §5): https://alpaca.markets/learn/building-a-multi-agent-ai-trading-system-on-alpaca

---

## 10. Open Items / To Verify

- [x] Does "Documents submitted: In review" block paper-trading order placement? **No** — verified via `alpaca account get`: status ACTIVE, options_trading_level 3 (multi-leg allowed), buying_power $400k. Not blocked.
- [ ] Confirm depth of Alpaca's historical options data (affects backtest range).
- [ ] Confirm real-time vs delayed data access (Algo Trader Plus dependency).
- [ ] Confirm $500 social engagement prize posting requirement — 1 person or full team.
- [ ] **Kickoff at 8:30pm today** — join, note any additional files/rules dropped, add them to this repo.
- [ ] Create fresh dedicated paper account for final submission — don't reuse dev account `PA3HGXMPWZFU`.
- [ ] Prateek: gather PAN (foreign TIN) ahead of time for W-8BEN, in case of a win.

---

## 11. Current Account Status (dev/testing account — NOT final submission account)

- Paper account: `PA3HGXMPWZFU`
- Starting balance: $100,000
- API endpoint: `https://paper-api.alpaca.markets/v2`
- ⚠️ Dashboard shows "Documents submitted: In review — up to 24-72 hours." Unconfirmed if this blocks order placement during review — verify first.

---

## 12. Build Plan

- **Day 1 (today, post-kickoff):** Confirm stack, get MCP server running against dev account, verify one full round-trip: `get_option_chain` → reasoning → `place_option_order` on a test trade.
- **Day 2-3:** Build full loop — scheduler, risk-gate middleware, audit logging. One complete cycle working end-to-end.
- **Day 4:** Run on dev account, observe behavior, fix risk-gate edge cases and bad LLM decisions.
- **Day 5:** Spin up fresh competition account with $100k, clean run, write one-pager from audit log, record demo.

---

## 13. Working Conventions for This Repo

- Keep `risk_gate.py` LLM-free, deterministic, unit-testable in isolation — this is the module judges/reviewers will scrutinize most for "risk gates are real."
- Every trade cycle (proposed, gated, executed or rejected) must write a structured audit log entry — this feeds both the demo and the one-pager, don't bolt it on later.
- Don't reach for LangGraph/CrewAI/etc unless the loop genuinely needs multi-agent orchestration (see §5 stretch goal) — plain Python async covers the core loop and matches what Alpaca's own reference implementation did.
- No training custom ML models on the critical path (see §7).
- Additional hackathon files dropped tonight at kickoff go in repo root — flag them and fold relevant instructions into this file.
