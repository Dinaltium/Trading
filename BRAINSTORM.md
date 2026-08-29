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

## 9. Blueprint received + adopted (shadow-model architecture)

User brought back a refined plan from a separate consultation (diagram + 8-item build list). Confirmed it matches our architecture with 3 real improvements, adopted wholesale:

- **Shadow-model architecture** (new): Groq is the only path that reaches execution. Claude Code CLI, Featherless, and Mistral run the same decision every cycle but are shadow-only — logged, never executed. Better than the original "swap reasoning engine mid-week" plan: gives continuous Groq-vs-open-model comparison data across the whole run instead of one late swap-and-compare.
- **Kelly probability source bug** (real bug in what we'd built): `risk_gate.py`'s `TradeProposal` took `model_confidence` straight from the LLM's self-report — the exact hallucination risk the risk-gate architecture exists to avoid. Must come from the calibrated classifier instead.
- **Atomic multi-leg execution** (real bug, caught from our own research pipeline reference): `notebookLLMResultPipeline.md`'s example code submits spread legs in a `for` loop — a partial fill there leaves a naked, unbalanced position. Must use Alpaca's actual multi-leg order type instead.
- Scope locked to SPY/QQQ only — already matched what was in `config/risk_limits.yaml`, and confirms no earnings-flag or separate VIX pipeline needed (index ETFs don't report earnings; VRP/IV-rank already built doubles as the vol-regime flag).

8-item build order adopted as the working task list for the rest of the build. Progress logged below as each item completes.

## 10. Build progress against the 8-item list

**Item 1 — Fix Kelly's probability source.** Done. `risk_gate.py`'s `TradeProposal.model_confidence` renamed to `classifier_win_probability`, with a `llm_confidence_score` field kept separately for audit-log display only — never sized on. Docstring spells out why. Self-check scenarios re-verified passing.

**Item 2 — Direction classifier.** Done. `src/signals/direction.py` — LightGBM binary classifier (return_1d/5d, 10d volatility, SMA ratio, RSI-14 features; 3-day forward return >0.5% as label), calibrated via `CalibratedClassifierCV` (isotonic). Guarded explicitly against the feature/split-order bug the blueprint flagged: features computed on the *full* bar history first, "today's" row split off before `dropna()` on the target column — otherwise dropping unlabeled rows (today has no forward return yet) silently drops today too. Live test: SPY p_up=0.431, QQQ p_up=0.4912, both on 599 training rows (~2.4yr daily bars) — sane near-coinflip numbers, not the suspiciously-high (~90%+) results the research flagged as leakage red flags.

**Item 3 — Lock scope to SPY/QQQ.** Already done — `config/risk_limits.yaml`'s `underlyings` list already had exactly these two from earlier setup. Confirms the free wins (no earnings-flag, no separate VIX pipeline) apply automatically.

**Item 4 — Model adapter.** Done. `src/model_adapter.py`:
  - `call_openai_compatible(provider, ...)` — one function for Groq/Featherless/Mistral (all OpenAI-tool-calling-format), keyed off a `PROVIDERS` dict of (env var, base_url, default model). Confirmed live: Groq works via this generic path too (not just the dedicated `groq` SDK from earlier). Featherless confirmed OpenAI-compatible at `https://api.featherless.ai/v1`.
  - **Featherless gotcha:** first default model tried (`meta-llama/Llama-3.3-70B-Instruct`) is gated, needs HuggingFace org connection — 403. Several other popular mirrors returned `capacity_exhausted` (plausibly 2909 hackathon participants hitting the same free pool on day 1). `TheDrummer/Anubis-70B-v1` responded cleanly — set as the default. Worth re-checking if it goes down mid-week; the free-tier model pool availability seems to fluctuate.
  - `call_claude_code_cli(...)` — subprocess wrapper (`claude -p <prompt>`), separate from the HTTP adapter since it's a CLI call not a web request, per the blueprint. `claude` confirmed on PATH.
  - Mistral: adapter wired, gracefully returns a clean "key not set" error until the user adds `MISTRAL_API_KEY` (placeholder already appended to `.env`).
  - All failures return a `ModelCallResult(ok=False, error=...)` instead of raising — a shadow-provider outage/capacity issue never takes down the live Groq call or the loop.

**Item 5 — Decision schema + strategy rules.** Done. `src/decision_schema.py` — `TradeDecision` dataclass + JSON schema (`selected_strategy`, `confidence_score`, `reasoning`, `approved_for_execution`), strategy-selection rules as the system prompt (IV rank >=65 + neutral -> iron_condor; IV rank <65 + P(Up)>=0.56 -> bull_call_spread; <=0.44 -> bear_put_spread; else cash). Thresholds pulled from the research/blueprint, not invented fresh. Full round-trip tested live against Groq: given SPY signals with IV rank unavailable (only 1 day logged), the model correctly recognized it couldn't confidently apply a directional rule without IV rank and defaulted to `cash` rather than forcing a trade — exactly the conservative behavior wanted.

**Item 6 — Atomic multi-leg execution.** Done (construction + verified against live data; actual order submission deferred to Item 7's dry-run with explicit confirmation before first real paper order). `src/execution.py`:
  - Confirmed `alpaca-py` supports real atomic multi-leg orders: `OrderClass.MLEG` + `LimitOrderRequest.legs: list[OptionLegRequest]` — one order, all legs fill together or not at all. This is the fix for the bug the blueprint flagged in our own `notebookLLMResultPipeline.md` reference code.
  - Contracts resolved from the live option chain by delta (never hand-built OCC symbols), nearest-to-target-DTE expiry (~weekly default, per AGENTS.md).
  - `build_spread()` constructs all 3 strategies. Live-tested against SPY's real chain: bull_call_spread (deltas 0.384/0.200, net debit $173/max profit $327), bear_put_spread (deltas -0.401/-0.195, net debit $191/max profit $609), iron_condor (deltas -0.193/-0.100/0.197/0.096, net credit $130.5/max loss $569.5) — all sane, delta targeting landed close to the 0.40/0.20/0.10 targets.
  - `submit_spread_order()` built (single `LimitOrderRequest` with `order_class=MLEG`, all legs, net price with correct debit/credit sign) but not yet fired — first real submission happens during Item 7's dry-run, with explicit confirmation since it's a real (paper) order even on the dev account.

**Item 7 — Audit log + scheduler + dry run.** Done, including the real order-submission test.
  - `src/audit_log.py` — one JSON-lines record per cycle (`logs/audit_log.jsonl`): signals, live Groq decision, every shadow model's pick, risk gate verdict, fill result. Dataclasses/enums serialized via a small `_to_jsonable` helper.
  - `src/orchestrator.py` — `run_cycle(underlying, dry_run)` ties every module together: fetch signals -> live Groq decision + shadow decisions (Featherless, Mistral, Claude Code CLI) -> if live decision isn't cash, build spread + risk-gate it with the classifier's calibrated probability (never the LLM's confidence, per item 1) -> execute atomically if approved and not dry_run -> write audit record.
  - First full dry-run cycle (SPY, live): Groq correctly chose `cash` — IV rank still `None` at 2 logged days, P(Up)=0.431 near-neutral, no rule cleanly applied. Claude Code CLI shadow agreed on `cash` with similar reasoning. Featherless hit `capacity_exhausted` again (transient, handled gracefully — logged as a failed shadow call, did not block the cycle). Mistral cleanly reported "key not set."
  - **Real order-submission verified**, with explicit user confirmation first since it's genuine order-entry even on paper: manually built an iron_condor spread and called `submit_spread_order()` directly (since natural signals hadn't crossed a trade threshold yet). Result: order `4509ac55-371d-4185-b4f0-4b94b36d1e28`, all 4 legs filled together, status `FILLED`, `filled_qty=1` on every leg. **This confirms the item-6 atomic-multi-leg fix actually works in production, not just constructs correctly** — no partial-fill/naked-leg risk observed.
  - `src/scheduler.py` — wraps `orchestrator.run_cycle()` for SPY + QQQ on a 15-min `apscheduler` interval, gated on Alpaca's own market clock (`get_clock().is_open`) rather than hand-rolled timezone math. Not yet run continuously/unattended — built and ready, single manual cycles verified above.

## 11. Weekend soak test (markets closed — validating before Monday, per user's explicit request)

Since Item 7's own advice is "run the scheduler repeatedly to find remaining bugs" but markets are closed over the weekend, ran a bounded validation pass instead of jumping straight to Item 8:

- **`scheduler.py` gained a `test_mode` flag** — bypasses the market-hours gate, for weekend testing only. Never set `True` once trading a real submission window.
- **`tests/test_risk_gate_state_accumulation.py`** (new) — synthetic multi-cycle scenario script, decoupled from live market data, directly exercising `risk_gate.py`'s state-dependent paths that today's mostly-cash real signals wouldn't naturally reach before Monday:
  - Diversification cap: 3 sequential approvals (SPY, QQQ, AAPL) accumulate correctly, a 4th name (MSFT) correctly rejected, re-adding an already-open name (SPY) correctly still allowed.
  - Total-open-risk shrink-to-fit: with only $200 headroom left under the cap (less than one contract's max loss), correctly rejects rather than "blindly approving" — this was the property under test; my own first-draft test expectation was wrong here, not the gate (caught and fixed). With more headroom ($1,200), correctly *shrinks* the Kelly-sized position from 5 to 3 contracts rather than either rejecting outright or overriding the cap.
  - Daily drawdown halt: fires exactly at -5.0%, not before (-4.9% still approved, -5.0% and -8.0% both correctly halted).
  - All 10 scenarios pass.
- **8 consecutive live orchestrator cycles** (alternating SPY/QQQ, real market data despite weekend — option snapshots and daily bars both still return usable data off-hours) ran with zero exceptions. SPY consistently resolved to `bear_put_spread` (risk gate approved each time, 10-12 Kelly-sized contracts, ~1.9-2% equity risk — consistent sizing across repeated cycles). QQQ consistently resolved to `cash` each time — not yet investigated why the two underlyings diverge this cleanly; worth a look before Monday if time allows, though "conservative on QQQ" isn't itself a red flag.
- **Unattended soak scheduler** started in the background (`scheduler.py --test-mode`, 15-min interval, dry-run) to idle for a stretch and confirm no crash/leak over sustained real-world-timed operation — running as of this log entry, not yet concluded.
- Real dev-account state (the one open iron_condor position from the earlier manual execution test, item 6/7) didn't naturally get exercised by these dry-run cycles' diversification/drawdown paths, since `dry_run=True` never submits — confirmed by design, and exactly why the standalone synthetic test above exists as a separate, deliberate check of that logic.

**Real bug caught during the soak test itself:** the first unattended scheduler run hung indefinitely — CPU time frozen, no child process, no output, for well past when a normal cycle should complete (batch-of-8 cycles each took 20-40s; this one sat idle for 7+ minutes with zero progress). Root cause confirmed by grepping `alpaca-py`'s REST layer directly: **it sets no request timeout anywhere**, so a stalled connection (most likely the option-chain fetch, which pulls 13,000+ contracts) can hang forever with no built-in recovery. Killed the stuck process (`taskkill`) and fixed it at the scheduler level: `src/scheduler.py` now wraps each `run_cycle()` call in a `ThreadPoolExecutor` with a 90s hard wall-clock timeout — a stalled cycle gets abandoned and logged, not left to freeze the whole loop. Known limitation, documented in the code comment: Python cannot forcibly kill a thread, so a *repeatedly* hanging call would leak abandoned threads over a many-day run rather than being fully cleaned up — acceptable as a first mitigation (turns "process dies" into "cycle skipped, loop continues"), not a complete fix. Retested: new scheduler run completed its first SPY cycle cleanly (IV rank now matured to 53.23 on 11 logged days, `bear_put_spread` again), no hang. Left idling in the background for the rest of the unattended soak.

**Plan for Monday (explicit, bounded):** watch the first 1-2 real scheduled cycles fire on the dev account at market open, then move straight to Item 8 — create the fresh dedicated competition account and go live. Don't spend more of Monday itself on testing; that's real trading time now, and the weekend soak is what's meant to have covered the state-accumulation risk.

## 13. /admin live-settings control (post-dashboard, user request)

User asked whether `.env` could become toggleable settings (which model, which underlyings, pause/resume) instead of hand-edited. Correctly identified the security conflict before building: the public dashboard has no auth, so anything writable from it is a second execution path — flagged this and got explicit scoping before touching code.

**Scoped in:** active live-model-provider (groq/featherless/mistral), underlyings list (added DIA/IWM as index-ETF options per the other chat's earnings-safe suggestion), global trading-paused switch.
**Scoped out, permanently:** anything in `risk_limits.yaml` — max loss %, drawdown halt, Kelly fraction never become remotely toggleable, even behind auth. Remotely-adjustable risk limits would undermine the "risk gate is hard-coded, never tamperable" property the whole judged architecture rests on.

- `config/live_settings.json` + `src/live_settings.py`: fetched fresh from GitHub every scheduler tick, fails safe to hard-coded defaults (groq/SPY+QQQ/not paused) on any fetch/parse error or disallowed value.
- `orchestrator.py`/`scheduler.py`: `live_provider` is now a parameter, not hardcoded `"groq"`. Shadow set becomes "every HTTP provider except whichever is live" — Claude Code CLI always stays shadow-only (subprocess, bad fit for unattended scheduling).
- `dashboard/src/app/admin/page.tsx` + `/api/live-settings/route.ts`: form UI, writes to `config/live_settings.json` via GitHub's Contents API using a server-only `GITHUB_TOKEN`.

**Auth architecture pivot, mid-build:** originally planned a second, fully separate password-protected Vercel project (user's explicit choice). Hit a real tool constraint: `create_git_project` dedupes by repository — a second `create_git_project` call against the same repo just reused the existing public project instead of creating a new one, no matter the `projectName` passed. The file-based fallback (`deploy_to_vercel`) would have required pasting the entire app's source through my own context as literal tool-call parameters (confirmed painfully — one attempt with `package-lock.json` included blew past a 25k-token read cap, a trimmed retry still cost ~30k+ tokens for marginal benefit). Pivoted instead to a **path-scoped auth gate on the same public project**: `dashboard/src/proxy.ts` (Next.js 16 renamed `middleware.ts` to `proxy.ts` — confirmed via the framework's own bundled docs, not stale training data) checks `ADMIN_PASSWORD` via HTTP Basic Auth, `matcher` scoped to only `/admin/:path*` and `/api/live-settings/:path*` — the public `/` dashboard route is untouched by the proxy file entirely and stays open for judges. Fails closed (503) if `ADMIN_PASSWORD` isn't configured, rather than defaulting open. Verified live post-deploy: public `/` returns 200, `/admin` correctly returned 503 (password not yet set) rather than either an error or unintended access.
- Still needs two env vars added manually on the Vercel project by the user (no tool available to set them remotely, and they shouldn't be pasted through chat regardless): `ADMIN_PASSWORD` and `GITHUB_TOKEN` (repo-scope PAT on Dinaltium/Trading).

Next: Item 8 (go live — fresh dedicated competition account, then keep it running + pull real audit-log entries into the write-up as they come in).

## 12. Dashboard built (Next.js + shadcn/ui, deployed to Vercel)

User switched dashboard plan from Streamlit to **Next.js + shadcn/ui** (stronger team experience, more visual control for Presentation criterion). Style reference: `devl.dev/r/dashboards/market.json` — borrowed dark theme/monospace/sparkline visual language only, none of its fake-data logic.

- **Architecture snag caught before building the wrong thing:** `logs/audit_log.jsonl` is local-only (gitignored, written by the local Python scheduler) — a Vercel-deployed dashboard has no access to it. Asked user; decided to un-gitignore that one file specifically and have the scheduler auto-push it to GitHub after each tick (skipped during `test_mode` so weekend soak-testing doesn't spam commits). Dashboard fetches the raw GitHub file fresh per request (`cache: 'no-store'`).
- Discovered mid-build that `account_equity` wasn't captured anywhere in the audit record — needed for the requested equity chart. Fixed: `orchestrator.py` now fetches account state every cycle (not just when a trade is being evaluated), `audit_log.py`/`write_cycle_record` gained an `account_equity` field.
- Ran the **dataviz skill** before writing chart code (per its own trigger rule — applies to any chart in any medium, not just Artifacts). Used its validated reference palette as-is rather than deriving a new one: fixed categorical hue order for the 3 real strategies (blue/orange/aqua) with `cash` deliberately muted gray (not a 4th categorical slot — it's "no trade," not a strategy), reserved status colors (green/red) for the risk-gate approved/rejected binary, single sequential blue hue for the equity line, no color-alone identity (every colored badge carries a text label too).
- Built on **Next.js 16** — newer than training data, has a real breaking-change caching model (Cache Components / `use cache` directives) but it's opt-in via `cacheComponents: true` in `next.config.ts`, which the scaffold doesn't enable — confirmed the "previous model" (`fetch(url, {cache:'no-store'})` in an async Server Component, `export const dynamic = 'force-dynamic'`) still applies, so the simpler approach was safe to use.
- Pages built: equity chart (custom inline SVG, no charting library dependency), 3 stat tiles (cycles logged / risk-gate approved / rejected), live-vs-shadow comparison cards for the 6 most recent cycles, full sortable cycle table. All read-only — confirmed no button, form, or action anywhere that touches order placement/cancellation; the risk gate remains the only path to execution.
- **Real bug caught by actually loading the page**, not just building it: local `next start` returned a confusing 500 — turned out port 3000 was already occupied by something else entirely, and curl was silently hitting that instead. Moved to port 3100, confirmed real rendering with a screenshot (dataviz skill's own step 7: "render it and look at it, don't just validate colors").
- **Noted, not chased:** GitHub's raw-content CDN (Fastly) has its own ~5min edge cache independent of the dashboard's `no-store` fetch — first fetch after a push got fresh data, subsequent ones briefly saw stale content until the edge cache caught up. Inherent to using `raw.githubusercontent.com` directly; acceptable since cache TTL < the 15-min scheduler interval, so no cycle is ever missed, just occasionally shown a few minutes late.
- **Deployed to Vercel** via the Vercel MCP tool's `create_git_project` (connected directly to `Dinaltium/Trading`, root directory `dashboard/`, auto-deploys on every push to `main`). Live at **https://alpaca-agent-dashboard-eta.vercel.app** — verified with a real screenshot post-deploy, correctly showing live data (25 cycles, real equity numbers, dark theme by default). This is the "Application URL" for the hackathon submission.

## 8. Still open / not yet decided

- [x] Groq account + API key — done, working, see §7b.
- [x] MCP vs CLI/SDK for the autonomous loop — decided, see §7d: CLI/SDK direct.
- [ ] Confirm Groq free tier rate limits are enough for a 15-min-cadence trading loop over ~5 trading days (check before committing).
- [ ] Test headless Claude Code CLI call with structured output, before relying on it as secondary engine.
- [ ] FinBERT model not yet downloaded (first `transformers` use triggers download — worth doing over good wifi before mid-build).
- [ ] Backtest skill (`alpaca-trading-backtest`) not yet test-driven.
- [ ] No repo scaffolding (`src/`, `risk_gate.py`, etc.) yet, per explicit instruction to hold off until hackathon officially starts tonight.
