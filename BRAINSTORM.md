# Brainstorm Log — Alpaca AI Trading Agents Hackathon

Running log of everything discussed/decided this session, in order. Not a build doc (see AGENTS.md for that) — this is the "why did we land here" record.

---

## 1. Problem statement (confirmed from hackathon page, full fetch)

Alpaca gives raw brokerage infra (Trading API, MCP server, CLI, paper accounts). Challenge: build an **autonomous AI agent** that trades on it.

3 hard-gated core requirements, all mandatory:
1. **Autonomous** — agent decides trades via Alpaca Trading API, not a human clicking.
2. **MCP or CLI** — must use Alpaca's MCP server or CLI as interface (not raw REST only).
3. **Options** — strategy must incorporate options trading.

Track: "Options Alpha Agents" — build agent generating P&L, clear testable strategy, show how it finds opportunities/decides/manages positions/performs over the week.

Judged 5 ways: P&L, Technology Implementation, Creativity & Originality, Presentation & Execution, Social Engagement.

## 2. Our solution shape (unchanged from initial plan, confirmed still correct)

Scheduler (~15min, market hours) → LLM reads Alpaca state via MCP tools → proposes options trade → hard-coded risk gate (non-LLM, deterministic) → execute or reject → audit log → loop.

Instruments: defined-risk spreads only (bull call, bear put, iron condor) — satisfies options requirement + gives a real, verifiable risk gate.

Signals: IV rank (Alpaca snapshot data) + technicals (pandas_ta_classic) + news sentiment (FinBERT).

## 3. P&L clarified

P&L = Profit and Loss vs starting $100k. Judges check final account equity/trade history against the Alpaca account ID submitted with the project — a real number, not a claimed one.

## 4. Account reset behavior clarified

Alpaca paper accounts CAN be reset (dashboard button, wipes balance + trade history back to configured start).

- **Dev account** (`PA3HGXMPWZFU`): reset freely, it's throwaway, not judged.
- **Final account** (created fresh, Day 5 per build plan): once real trading starts on it, do NOT reset — judges want to see performance *over the week*, not just an end number. Resetting late defeats "Presentation & Execution" and the "clear testable strategy... performs over the course of the competition" requirement.

So: mess around / iterate freely on dev account now. Final account's history, once started, stays intact till submission.

## 5. Reasoning-engine plan (decided this session — supersedes earlier "just use Anthropic API" plan)

Anthropic API costs money, no meaningful free tier for this. Considered options:
- lablab.ai's "$100 credits" banner — **ruled out, that's for a different hackathon**, doesn't apply here.
- Anthropic new-account trial credit (~$5) — too small to rely on.
- Claude Code CLI headless mode — reuses existing paid Claude Code subscription, no separate API billing.
- Groq free-tier API (hosted open-source models, e.g. Llama) — genuinely free, fast inference.

**Decided plan:**
1. **Groq = primary.** Build and validate the full loop against Groq first (structured proposal output, MCP tool orchestration, risk gate integration). Get this working well before touching Claude.
2. **Claude Code CLI (headless) = secondary.** Once Groq loop is solid, swap the reasoning engine to Claude Code and run the same loop. Compare behavior/quality — this becomes a documented open-source-vs-paid-model comparison, which is a strong "Creativity" + "Technology Implementation" story for judging (shows deliberate engineering choice, not just "we called an API").
3. **Local GPU model (4-10B params, e.g. Qwen2.5-7B-Instruct or Llama-3.1-8B-Instruct via Ollama) = optional stretch.** Only pursue if Groq and Claude Code paths are both working and there's time left. Risk: small local models are weaker at structured JSON output and multi-step tool-calling, and GPU/quantization setup costs build time we don't have much of. Don't let this block the core loop.

Rationale for Groq-first ordering: de-risks the core loop (scheduler, MCP tool calls, risk gate, audit log) against a free, fast, zero-cost-of-iteration model before spending anything on Claude. By the time we switch to Claude, the loop plumbing is already proven, so Claude's turn is just a reasoning-quality swap, not a rebuild.

## 6. New submission requirements found on full page re-read

Not in original README, discovered via full page fetch:

- Public **GitHub repo** required, MIT-compliant license.
- **Cover image + video presentation + slide presentation** all required deliverables, not just the one-pager.
- **Alpaca paper trading account ID must be submitted** — judges trade-verify P&L directly against it.
- Social engagement is now a **judging criterion**, not just a separate prize track — up to 5 X/LinkedIn post links, must tag @lablabai and @AlpacaHQ.
- Confirmed kickoff schedule tonight (IST): 8:30 kickoff → 8:35 lablab.ai words → 8:40 Alpaca words → 8:45 challenge intro → 8:55 hackathon guide → 9:30 Discord Q&A.
- Dev account free to use during build; final submission account must be brand-new, created right before final run (this matches what we already had).

## 7. Environment setup done this session

- Alpaca CLI v0.0.13 installed, profile "paper" configured, connectivity confirmed (`alpaca doctor` — all checks passed).
- Dev account `PA3HGXMPWZFU` confirmed ACTIVE, options_trading_level 3 (multi-leg allowed), $100k cash / $400k buying power. "Documents in review" banner does NOT block trading — verified directly.
- 4 Alpaca skills installed: `alpaca-trading-backtest`, `alpaca-trading-paper-trading` (generic/CLI/MCP variants).
- Python venv created (`.venv`, Python 3.10.11) in repo root.
- Installed: `alpaca-py` 0.44.0, `pandas-ta-classic` 0.6.52, `transformers` 5.16.1, `torch` 2.13.0 (CPU), `apscheduler`, `python-dotenv`, `pyyaml`.
- **Gotcha found:** PyPI package `pandas-ta` is dead/unmaintained, won't install on Python 3.10. Use maintained fork `pandas-ta-classic` instead — but it imports as `pandas_ta_classic`, NOT `pandas_ta`. Already noted in AGENTS.md tech stack table.
- `requirements.txt` frozen (55 packages) for reproducibility.

## 7b. Groq confirmed working

- `GROQ_API_KEY` added to `.env`, loaded via `python-dotenv`. `groq` SDK installed.
- Model catalog on this key (checked live, don't trust old model names like `llama-3.3-70b-versatile` — 404s, deprecated): `groq/compound-mini`, `groq/compound`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `openai/gpt-oss-safeguard-20b`, `qwen/qwen3.6-27b`, `qwen/qwen3.8-27b`, `allam-2-7b`, `whisper-large-v3` (+turbo, audio), plus prompt-guard/orpheus utility models.
- **Chosen model: `openai/gpt-oss-120b`** — largest available, test call returned correct output, `tool_calls` field present in response schema (OpenAI-compatible tool/function calling supported — needed for MCP-style orchestration).
- **Gotcha:** gpt-oss models emit a hidden `reasoning` field in the message *before* `content` and both count against `max_tokens`. A low `max_tokens` (tested at 10) truncates before `content` is ever written, giving an empty-looking response. Use a generous `max_tokens` budget (200+) in the real loop, and always read `.content`, not assume it's the only field.

## 7d. MCP vs CLI/SDK decision for the autonomous loop (hackathon officially started, Day 1 begins here)

Read `alpaca-trading-paper-trading-mcp` skill in full. Key finding, from the skill itself: it's written for an **interactive Cursor-hosted MCP session** (`GetDynamicTools`, config at `~/.cursor/mcp.json`), and it explicitly says for our case:

> "MCP servers are session-based... For production-grade automation, use the Alpaca SDK directly... Standalone automation leaves this skill's guarantees behind."

Also critical: standalone scripts get none of the skill's paper-mode gate protection — a live account returns the same response shape as paper, silently. Must assert `paper=True` as a literal in code at client construction, not read from config, and abort if a live flag is present.

**Decided:** autonomous scheduler loop uses **`alpaca-py` SDK directly**, exposed to Groq as structured tool-call functions (`get_option_chain`, `place_option_order`, etc. — OpenAI-compatible function calling, confirmed supported by Groq's `tool_calls` field in §7b). This satisfies the hackathon's "MCP or CLI" requirement via the **CLI/SDK path**, not literal MCP-protocol calls. Keep the actual `alpaca-mcp-server` available separately for interactive manual testing/debugging in Claude Code sessions — not part of the production loop. Simpler, fewer moving parts to debug this week, matches the skill's own guidance for unattended scripts.

This slightly revises AGENTS.md §5's original framing ("MCP server is the LLM's only interface to Alpaca") — the interface is now the SDK via tool-calling; MCP stays available as a dev-time tool, not the runtime path.

## 7e. .env cleanup + SDK connection confirmed (Day 1 build start)

- Found `ALPACA_API_KEY` in `.env` held a mis-pasted **Featherless AI key** (`rc_...`, 67 chars — wrong format for an Alpaca key, which is ~26 chars). Flagged before overwriting.
- User confirmed: Featherless credits did come through, revoked the old key, re-added it correctly as `FEATHER_API_KEY`.
- Filled correct `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` into `.env` programmatically from the CLI's own profile config (`~/.config/alpaca/profiles/paper.yaml`) — never printed the raw values, compared by SHA-256 fingerprint/length instead.
- `alpaca-py` SDK connection confirmed working end-to-end: `TradingClient(...).get_account()` returns ACTIVE, account `PA3HGXMPWZFU`, options level 3 — matches CLI's earlier result.
- `.env` now holds all 4 needed keys: `GROQ_API_KEY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `FEATHER_API_KEY`.

## 7f. Repo scaffold started (hackathon officially live, Day 1 build)

- Created `src/`, `src/signals/`, `config/`, `backtests/`, `logs/`, `writeup/` per AGENTS.md §8 target structure.
- `config/risk_limits.yaml` — all hard limits from AGENTS.md §6, plus Kelly-sizing params (`kelly_fraction: 0.25` quarter-Kelly, `kelly_cap_pct`) per the model-research consensus (§5).
- `src/risk_gate.py` built and self-tested — deterministic, LLM-free, dataclass-based (`TradeProposal`, `AccountState`, `GateResult`). Checks: allowed strategy, daily drawdown halt, underlying diversification cap, Kelly-fraction sizing (rejects negative-edge trades), total-open-risk cap with graceful shrink-to-fit. 5 self-check scenarios all passed correctly on second pass (first pass caught a bug in my own test data, not the gate logic — see below).
- **Gotcha caught while testing:** initial "should-approve" test scenario used `model_confidence=0.62` with a payoff ratio (`max_profit/max_loss` = 150/350 = 0.43) whose breakeven win probability is ~70% — so the gate correctly rejected it as negative-edge. Not a bug in `risk_gate.py`; the test data was wrong. Fixed by using `model_confidence=0.78`. Worth remembering when hand-writing more test trades later: for a payoff ratio *b* < 1 (typical credit spread/iron condor shape), breakeven win-rate is `1/(1+b)`, higher than intuition suggests.

## 7g. Volatility signal module built + live data confirmed

- Confirmed empirically (not just from research docs): Alpaca's `OptionBarsRequest` (historical) returns OHLCV only, no `implied_volatility` field. Live `OptionChainRequest` snapshot DOES carry `implied_volatility` + full Greeks (delta/gamma/theta/vega/rho) per contract. Matches the research consensus in section 5 exactly.
- Built `src/signals/iv_rank.py`: `compute_vol_signals()` returns current ATM IV (nearest-strike from live chain), 20-day realized vol (from stock bars, annualized), VRP (their difference), and IV Rank/Percentile computed from a growing local CSV log (`logs/iv_history_<underlying>.csv`) — logs one row per call, reports its own sample size so it's never silently treated as a full 52-week rank.
- Live test against SPY: price $769.615, ATM IV 8.92%, 20d realized vol 10.39%, VRP -1.47 vol pts (mildly inverted — per research regime rules this leans toward a long-vol setup, not premium-selling). IV rank correctly `None` at 1 logged day — will start reporting once 5+ days accumulate through the week.
- Design deliberately skips building a Black-Scholes backfill (`py_vollib` reconstructing historical IV from historical option OHLC + underlying price) to get an instant 52-week IV history — flagged as possible but too heavy for Day 1, per the option chain expiring/rolling problem making a clean backfill non-trivial. VRP carries the volatility signal early in the week; IV rank strengthens as logging accumulates.

## 8. Still open / not yet decided

- [x] Groq account + API key — done, working, see §7b.
- [x] MCP vs CLI/SDK for the autonomous loop — decided, see §7d: CLI/SDK direct.
- [ ] Confirm Groq free tier rate limits are enough for a 15-min-cadence trading loop over ~5 trading days (check before committing).
- [ ] Test headless Claude Code CLI call with structured output, before relying on it as secondary engine.
- [ ] FinBERT model not yet downloaded (first `transformers` use triggers download — worth doing over good wifi before mid-build).
- [ ] Backtest skill (`alpaca-trading-backtest`) not yet test-driven.
- [ ] No repo scaffolding (`src/`, `risk_gate.py`, etc.) yet, per explicit instruction to hold off until hackathon officially starts tonight.
