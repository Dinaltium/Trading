# Options Alpha Agent

Autonomous AI options-trading agent built for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) (lablab.ai × Alpaca, Aug 28–Sep 4, 2026), Options Alpha track.

**Live dashboard:** https://alpaca-trade-intelli.vercel.app (public, read-only)
**Deeper docs:** [`docs/playbook.html`](docs/playbook.html) (full architecture walkthrough) · [`docs/markets101.html`](docs/markets101.html) (options/markets basics, no finance background assumed)

---

## Problem statement

Build an autonomous AI agent that trades options on Alpaca's paper-trading environment. Three hard requirements from the hackathon: the agent must be genuinely autonomous (no human clicking per trade), it must use Alpaca's Trading API via the MCP server or CLI, and every strategy must incorporate options — not just stocks.

## Our solution

A robot that watches SPY and QQQ options every 15 minutes, gets a cautious trade proposal from an AI model, and only lets that trade through if a separate, hard-coded, non-AI rulebook agrees it's safe. The AI reasons in words; a deterministic risk gate has final veto power over anything it proposes — no LLM ever does the math that decides how much money moves.

Four AI models see the exact same signals every cycle. Only one — Groq — is ever allowed to execute. The other three run in shadow: their decisions are logged for comparison and never touch the account. This turns "which model is better" into a continuously-collected, honest benchmark instead of a claim.

---

## The pipeline

```
Every 15 minutes, market hours (runs on GitHub Actions — not anyone's laptop):

  1. Pull live price + option chain from Alpaca
  2. Compute signals: IV Rank, VRP (volatility), LightGBM P(Up) (direction)
  3. Send those signals to 4 AI models in parallel
       Groq          → LIVE, can execute
       Claude Code CLI, Featherless, Mistral → shadow, logged only
  4. Groq's decision goes to the risk gate (plain Python, zero AI):
       Kelly-criterion sizing · max loss % · drawdown halt · diversification cap
       → approved: build the spread, submit as ONE atomic multi-leg order
       → rejected: nothing happens, logged
  5. Everything (signals, all 4 decisions, risk verdict, fill result) is written
     to one audit-log record, pushed to GitHub
  6. Dashboard reads that file fresh on every page load
```

## Models & algorithms

| Component | What it is | Role |
|---|---|---|
| **Direction signal** | LightGBM binary classifier, isotonic-calibrated, walk-forward retrained | Outputs P(Up) — the only quantitative number the AI reasons with |
| **Volatility signal** | IV Rank + Volatility Risk Premium (VRP), computed from Alpaca's live option chain | "Is volatility expensive right now" |
| **Live reasoning (executes)** | [Groq](https://groq.com) — free, fast open-model inference | Picks one of: bull call spread / bear put spread / iron condor / cash |
| **Shadow reasoning (logged only)** | Claude Code CLI, [Featherless](https://featherless.ai), [Mistral](https://mistral.ai) | Same signals, same rules, never executes — pure benchmark data |
| **Risk gate** | Deterministic Python, Kelly-criterion position sizing off the calibrated classifier probability (never an LLM's self-reported confidence) | Final, non-AI approval/rejection on every proposed trade |
| **Execution** | `alpaca-py`, atomic multi-leg orders | All legs of a spread fill together or not at all — no partial-fill risk |

Full rationale for every one of these choices — why Groq-primary, why the risk gate is deliberately not AI, why atomic orders, why SPY/QQQ — is in [`docs/playbook.html`](docs/playbook.html).

## Benchmark

Model-comparison benchmark (Groq vs. Claude Code CLI vs. Featherless vs. Mistral, same signals, same cycle, every 15 minutes across the full competition window) — **results to be published at the end of the hackathon**, once a full week of paired live/shadow decisions has accumulated. Live data is visible today on the [dashboard](https://alpaca-trade-intelli.vercel.app) under "Live vs. shadow."

A separate historical backtest validating the direction signal across 6 underlyings (SPY, QQQ, DIA, IWM, AAPL, TSLA) is already complete — see [`runs/2026-08-29_multi-symbol_lightgbm-direction_1Day/report.md`](runs/2026-08-29_multi-symbol_lightgbm-direction_1Day/report.md).

---

## Progress

- [x] Risk gate — deterministic, Kelly-sized, 10/10 synthetic scenarios passing
- [x] Direction classifier — LightGBM, calibrated, live-tested
- [x] Volatility signals — IV Rank + VRP, live against Alpaca's option chain
- [x] 4-model reasoning adapter — Groq/Featherless/Claude Code CLI live-tested, Mistral wired
- [x] Atomic multi-leg execution — verified with a real filled order on the dev account
- [x] Audit log + GitHub Actions — trading loop runs automatically every 15 min, no laptop required
- [x] Public read-only dashboard — live equity chart, full AI reasoning, risk-gate history
- [x] Password-gated `/admin` settings (active model / underlyings / pause switch — never risk limits)
- [x] Multi-symbol backtest — validated signal quality across 6 underlyings
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
│   ├── signals/               # direction (LightGBM) + volatility (IV Rank/VRP)
│   ├── risk_gate.py             # deterministic, non-AI risk rules
│   ├── model_adapter.py          # Groq/Featherless/Mistral + Claude Code CLI
│   ├── decision_schema.py         # shared prompt + rules given to every model
│   ├── execution.py                # atomic multi-leg spread construction/submission
│   ├── orchestrator.py              # ties one cycle together
│   ├── scheduler.py                  # runs a cycle every 15 min (local or Actions)
│   ├── audit_log.py                   # writes + pushes the cycle log
│   └── live_settings.py                # remote-toggleable, non-risk settings
├── config/
│   ├── risk_limits.yaml       # hard risk numbers — hand-edited only, never remote
│   └── live_settings.json      # active model / underlyings / pause — via /admin
├── dashboard/                 # Next.js + shadcn/ui, deployed to Vercel
├── .github/workflows/         # GitHub Actions — the actual always-on trading loop
├── runs/                      # backtest run artifacts (data, reports, disclosures)
├── docs/                      # standalone HTML explainers (playbook, markets basics)
├── AGENTS.md                  # full build guidance for AI coding agents working here
└── BRAINSTORM.md              # running log of every decision made and why
```

---

## Disclosures

This project trades exclusively on Alpaca's **paper trading** environment — simulated funds, real market data, no real money at risk. Paper trading results are hypothetical and do not represent actual trading performance or guarantee future results. Nothing here is investment advice. See [Alpaca's disclosures](https://alpaca.markets/disclosures).
