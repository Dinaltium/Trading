# Options Alpha Agent

Autonomous AI options-trading agent built for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) (lablab.ai × Alpaca, Aug 28–Sep 4, 2026), Options Alpha track.

**Live dashboard:** https://alpaca-trade-intelli.vercel.app (public, read-only)
**Deeper docs:** [`docs/graveyard.md`](docs/graveyard.md) (every defect this agent had, and what now catches it) · [`docs/playbook.html`](docs/playbook.html) (full architecture walkthrough) · [`docs/markets101.html`](docs/markets101.html) (options/markets basics, no finance background assumed) · [`docs/architecture.svg`](docs/architecture.svg) (one-page system diagram)

---

## Problem statement

Build an autonomous AI agent that trades options on Alpaca's paper-trading environment. Three hard requirements from the hackathon: the agent must be genuinely autonomous (no human clicking per trade), it must use Alpaca's Trading API via the MCP server or CLI, and every strategy must incorporate options — not just stocks.

## Our solution

A robot that watches SPY and QQQ options every 15 minutes, gets a trade proposal from an AI model, and only lets it through if separate, hard-coded, non-AI code agrees. The AI reasons in words; no LLM ever does the math that decides how much money moves.

The model's authority is deliberately narrow, and this is the core design claim: **a model may decline a trade the rules mandate, but it can never propose one they don't.** A deterministic rulebook maps every possible signal combination to exactly one strategy. The model returns that strategy or it returns cash. Anything else is rejected in Python — re-derived from the raw signals rather than from the model's own summary of them. Discretion to decline, not to substitute.

Three AI models see the exact same signals every cycle. Only one is live; the other two run in shadow, logged and never touching the account. Every one of the three is scored against the rulebook on every cycle, so "which model is better" becomes counted evidence rather than a claim. It was four until two providers turned out to be unreachable unattended for different reasons - both are documented in the graveyard rather than quietly dropped.

Around that sits an integrity layer — four guards that assume the agent's own inputs and outputs can be wrong or fabricated. See below.

---

## The pipeline

```
Every 15 minutes, market hours (one GitHub Actions job per session — not anyone's laptop):

  1. Pull live price + option chain from Alpaca
  2. Compute signals: IV Rank, VRP (volatility), LightGBM P(Up) (direction)
  3. GUARD 1 — validate the signal vector. Out of range, NaN or internally
     inconsistent, and no model is consulted at all
  4. Send those signals to 3 AI models in parallel
       Groq          → LIVE, can execute      (configurable from /admin)
       Featherless, Mistral → shadow, logged only
  5. GUARD 2 — faithfulness. Every signal figure the live model quotes in its
     reasoning must match what it was handed. A fabricated number kills the trade
  6. GUARD 3 — cross-validation. Record how many of the independent models
     reached the same answer
  7. RULEBOOK — reject any strategy the deterministic rules do not mandate
  8. RISK GATE (plain Python, zero AI):
       Kelly sizing off the calibrated classifier · max loss % · drawdown halt ·
       diversification cap · premium-selling halt
  9. GUARD 4 — reconcile the agent's position map against a SECOND, independent
     read of broker state. Disagreement blocks the order
 10. Submit via the Alpaca CLI: paper endpoint re-verified out-of-process, dry-run
     first, then ONE atomic multi-leg order with a client order ID for idempotency
 11. Everything — signals, 4 decisions, 4 guard verdicts, rulebook ruling, risk
     verdict, fill result — is written to one audit record and pushed to GitHub
 12. Dashboard reads that file fresh on every page load
```

## Models & algorithms

| Component | What it is | Role |
|---|---|---|
| **Direction signal** | LightGBM binary classifier, isotonic-calibrated, walk-forward retrained | Outputs P(Up) — the only quantitative number the AI reasons with |
| **Volatility signal** | IV Rank + Volatility Risk Premium (VRP), computed from Alpaca's live option chain | "Is volatility expensive right now" |
| **Live reasoning (executes)** | [Groq](https://groq.com) — free, fast open-model inference | Picks one of: bull call spread / bear put spread / iron condor / cash |
| **Shadow reasoning (logged only)** | [Featherless](https://featherless.ai), [Mistral](https://mistral.ai) | Same signals, same rules, never executes — pure benchmark data |
| **Rulebook** | Deterministic decision table over (IV Rank, P(Up)), exhaustive by construction | The model may match it or choose cash — nothing else survives |
| **Risk gate** | Deterministic Python, Kelly sizing off the calibrated classifier probability (never an LLM's self-reported confidence) | Final, non-AI approval/rejection on every proposed trade |
| **Integrity guards** | Four deterministic checks structured on TradeTrap's attack-surface taxonomy | Signal validation, faithfulness, cross-validation, reconciliation |
| **Event trigger** | AZTE rolling z-score, log-only for now | Records which cycles carried real information |
| **Execution** | Alpaca **CLI**, atomic MLEG orders, dry-run verified, idempotent | All legs fill together or none do — no partial-fill risk |

Full rationale for every one of these choices — why Groq-primary, why the risk gate is deliberately not AI, why atomic orders, why SPY/QQQ — is in [`docs/playbook.html`](docs/playbook.html).

## The integrity layer

Most of the failure modes in an LLM trading agent are not "the model picked a bad trade". They are the model reasoning confidently about a number that was already wrong, or the agent acting on a position map that no longer matches reality. Four deterministic guards ([`src/guards.py`](src/guards.py)), each mapped to a component of the TradeTrap taxonomy:

| Guard | Catches | Blocks? |
|---|---|---|
| **Signal validation** | Out-of-range, NaN, or internally inconsistent signals — before any model is consulted | Yes |
| **Faithfulness** | The live model quoting a signal value it was never given | Yes |
| **Cross-validation** | The live model as the lone dissenter against three independent shadows | Records |
| **Reconciliation** | The agent's position map disagreeing with a second, independent read of broker state | Yes |
| **Circuit breaker** | Repeated execution failures — persisted to disk, so it survives the restart between cycles | Yes |

None of them calls a model. A guard that asked an LLM whether the LLM was lying would defeat its own purpose.

The signal guard earns its place concretely: it independently flags the exact degenerate-IV-window condition that silently pinned `iv_rank` at 100 and sent 47 of 47 elevated-volatility cycles to cash before it was found by hand.

### On look-ahead bias

[Look-Ahead-Bench](https://arxiv.org/abs/2601.13770) shows that an LLM scored on historical data may be reciting memorised outcomes rather than predicting, producing backtested alpha that evaporates live. **This agent is immune by construction:** it decides only on data timestamped at or before the decision instant, and is scored on outcomes that have not yet happened. Every audit record stamps `decision_time` and `data_cutoff` so that claim is checkable rather than asserted.

### Research this implements

| Paper | What we took |
|---|---|
| [TradeTrap](https://arxiv.org/abs/2512.02261) (Yan et al., Shanghai AI Lab) | The four-component attack-surface taxonomy and its named mitigations — the structure of [`src/guards.py`](src/guards.py) |
| [AgenticAITA](https://arxiv.org/abs/2605.12532) (Letteri) | Deterministic safety constraints bounding agent behaviour independently of LLM stochasticity; AZTE selective activation ([`src/signals/azte.py`](src/signals/azte.py)) |
| [Look-Ahead-Bench](https://arxiv.org/abs/2601.13770) (Benhenda) | Temporal provenance stamping; forward-only live evaluation |

PDFs are not redistributed in this repo — they are the authors' copyrighted work. Follow the links.

## Benchmark

Model-comparison benchmark (Groq vs. Claude Code CLI vs. Featherless vs. Mistral, same signals, same cycle, every 15 minutes across the full competition window) — **results to be published at the end of the hackathon**, once a full week of paired live/shadow decisions has accumulated. Live data is visible today on the [dashboard](https://alpaca-trade-intelli.vercel.app) under "Live vs. shadow."

A separate historical backtest validating the direction signal across 6 underlyings (SPY, QQQ, DIA, IWM, AAPL, TSLA) is already complete — see [`runs/2026-08-29_multi-symbol_lightgbm-direction_1Day/report.md`](runs/2026-08-29_multi-symbol_lightgbm-direction_1Day/report.md).

---

## Progress

- [x] Risk gate — deterministic, Kelly-sized, 10/10 synthetic scenarios passing
- [x] Direction classifier — LightGBM, calibrated, live-tested
- [x] Volatility signals — IV Rank + VRP, live against Alpaca's option chain
- [x] 4-model reasoning adapter — Groq/Featherless/Claude Code CLI live-tested, Mistral wired
- [x] Atomic multi-leg execution via the **Alpaca CLI** — dry-run verified, idempotent, paper endpoint re-checked out-of-process before every order
- [x] Deterministic rulebook — exhaustive over the signal space; the model can decline but never substitute
- [x] Integrity guard layer — 4 guards on the TradeTrap taxonomy, plus a disk-persisted circuit breaker
- [x] Temporal provenance — every record stamps `decision_time` / `data_cutoff`
- [x] Test suite — 74 tests covering the gate, rulebook, guards, parsing, IV ranking and cross-cycle state
- [x] Audit log + GitHub Actions — trading loop runs automatically every 15 min, no laptop required
- [x] Public read-only dashboard — live equity chart, full AI reasoning, risk-gate history
- [x] Password-gated `/admin` settings (active model / underlyings / pause switch — never risk limits)
- [x] Multi-symbol backtest — validated signal quality across 6 underlyings
- [ ] Position management / exits — the agent currently only opens spreads; exit logic and a true exit-only kill switch are the largest remaining gap
- [ ] Live market-hours trading — markets closed over the prep weekend; first real cycles run when the market opens
- [ ] Fresh dedicated competition account — created right before the final submission run, per hackathon rules
- [ ] Model-comparison benchmark write-up
- [ ] Social media build-in-public posts

## What's next

- Decide QQQ vs. DIA in the live underlying set (backtest shows QQQ's signal is currently the weakest of the 6 tested — see the backtest report above)
- Run the loop through a full live trading week, let the audit log accumulate
- Publish the Groq-vs-open-model benchmark from real paired decisions
- Record the demo video, write the one-page submission summary
- Post build-in-public updates on X/LinkedIn (tagging @lablabai and @AlpacaHQ)

## Social

Build-in-public posts (X / LinkedIn) — **to be added here as they're published.**

---

## Running it

### Locally

```bash
git clone https://github.com/Dinaltium/Trading.git
cd Trading
python -m venv .venv
.venv\Scripts\activate          # Windows — use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt

cp .env.example .env            # then fill in real values, see below
```

Run one cycle manually (no real order placed):

```bash
python -c "from dotenv import load_dotenv; load_dotenv(override=True); from src.orchestrator import run_cycle; print(run_cycle('SPY', dry_run=True))"
```

Run the full autonomous loop (every 15 min, market hours):

```bash
python -m src.scheduler
```

### Where it actually runs

The trading loop is **not** dependent on any one machine — the exact same script (`src/scheduler.py`) runs automatically on **GitHub Actions** (`.github/workflows/trading-cycle.yml`), on a 15-minute cron during market hours, on GitHub's own servers. Because the repo is public, every cycle's full console output is visible in the repo's **Actions** tab — a live, unfiltered execution log anyone can watch, no laptop or access request needed.

Local runs still work identically and are useful for manual testing/debugging, but the system does not depend on your laptop being open.

### The dashboard

Next.js + shadcn/ui, in [`dashboard/`](dashboard/), deployed to Vercel: **https://alpaca-trade-intelli.vercel.app**. Reads the audit log fresh from GitHub on every page load — no caching, no build-time snapshot. Strictly read-only: no button, form, or action anywhere touches order placement. A separate `/admin` route (password-gated) lets the two of us toggle which model is live, which underlyings are active, and pause/resume — never risk limits, which stay hand-edited in `config/risk_limits.yaml` only.

---

## Environment variables

Copy [`.env.example`](.env.example) to `.env` and fill in:

| Variable | Required | Where to get it |
|---|---|---|
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | Yes | [alpaca.markets](https://alpaca.markets) → paper trading account → API Keys |
| `GROQ_API_KEY` | Yes | [console.groq.com](https://console.groq.com) — free |
| `FEATHER_API_KEY` | Yes | [featherless.ai](https://featherless.ai) — free tier |
| `MISTRAL_API_KEY` | No | [console.mistral.ai](https://console.mistral.ai) — optional, that shadow provider just reports "key not set" without it |

For the GitHub Actions workflow, the same keys are set as **repository secrets** (Settings → Secrets and variables → Actions), not in a committed file.

For the dashboard's `/admin` route: `ADMIN_PASSWORD` and `GITHUB_TOKEN` (repo-scope PAT), set as **Vercel environment variables** on the dashboard project — never in this repo.

---

## Repository structure

```
Trading/
├── src/                      # the trading agent
│   ├── signals/               # direction (LightGBM), volatility (IV Rank/VRP), AZTE trigger
│   ├── guards.py                # the integrity layer — 4 deterministic guards
│   ├── risk_gate.py              # deterministic, non-AI risk rules + rulebook enforcement
│   ├── decision_schema.py         # shared prompt AND the executable rulebook
│   ├── model_adapter.py            # Groq/Featherless/Mistral + Claude Code CLI
│   ├── alpaca_cli.py                # CLI execution + out-of-process paper-endpoint guard
│   ├── execution.py                  # spread construction from the live chain
│   ├── orchestrator.py                # ties one cycle together
│   ├── scheduler.py                    # runs a cycle every 15 min (local or Actions)
│   ├── agent_state.py                   # state that must survive the restart between cycles
│   ├── audit_log.py                      # writes + pushes the cycle log
│   └── live_settings.py                   # remote-toggleable, non-risk settings
├── config/
│   ├── risk_limits.yaml       # hard risk numbers — hand-edited only, never remote
│   └── live_settings.json      # active model / underlyings / pause — via /admin
├── dashboard/                 # Next.js + shadcn/ui, deployed to Vercel
├── .github/workflows/         # GitHub Actions — the actual always-on trading loop
├── logs/                      # audit log, IV history, agent state, archived evidence
├── writeup/                   # one-page submission write-up
├── runs/                      # backtest run artifacts (data, reports, disclosures)
├── docs/                      # HTML explainers + the architecture diagram
├── AGENTS.md                  # full build guidance for AI coding agents working here
└── BRAINSTORM.md              # running log of every decision made and why
```

---

## Disclosures

This project trades exclusively on Alpaca's **paper trading** environment — simulated funds, real market data, no real money at risk. Paper trading results are hypothetical and do not represent actual trading performance or guarantee future results. Nothing here is investment advice. See [Alpaca's disclosures](https://alpaca.markets/disclosures).
