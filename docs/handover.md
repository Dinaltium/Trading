# Handover — getting productive on this repo

For Prateek, or anyone picking this up cold. Read [`README.md`](../README.md) first for what
the system does; this is how to run it, what state it holds, and where the sharp edges are.

---

## 1. Setup

```bash
git clone https://github.com/Dinaltium/Trading.git
cd Trading
python -m venv .venv
.venv\Scripts\activate          # Windows.  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill it in. `.env` is gitignored and must stay that way.

```
ALPACA_API_KEY=...       # paper account
ALPACA_SECRET_KEY=...
GROQ_API_KEY=...         # the live reasoning model
FEATHER_API_KEY=...      # shadow
MISTRAL_API_KEY=...      # shadow
```

**Never commit a key, never paste one into chat or an issue.** If one leaks, revoke it in the
provider console first and regenerate second.

Order submission shells out to Alpaca's official CLI, which is a Go binary and not a pip
package:

```bash
go install github.com/alpacahq/cli/cmd/alpaca@latest
alpaca profile login --api-key --paper --name paper --key "$ALPACA_API_KEY" --secret "$ALPACA_SECRET_KEY"
alpaca doctor
```

`alpaca doctor` must print the paper endpoint. The agent re-runs that check out-of-process
before building any order — a deliberate second opinion from a binary we did not write.

---

## 2. Running it

```bash
python -m pytest tests/ -q          # 131 tests, should be green before you change anything
```

```bash
python -m src.orchestrator          # ONE dry cycle on SPY, prints the full record as JSON
```

```bash
python -m src.scheduler --once      # one full tick: exits, then every configured underlying
```

```bash
python -m src.scheduler --session --max-minutes 60   # the loop, as CI runs it
```

Flags that matter:

| Flag | Effect |
|---|---|
| *(none)* | `dry_run=True`. Real signals, real model calls, real risk verdict — **no order sent** |
| `--live` | actually submits paper orders |
| `--test-mode` | bypasses the market-hours gate for weekend testing. **Never writes IV history and never pushes the audit log** |
| `--session` | long-running mode; drives its own 15-min cadence, exits at the close |
| `--max-minutes N` | session time budget |

Start with no flags. `--live` is not a debugging tool.

---

## 3. Where things live

```
src/
  scheduler.py        market-hours loop; --once and --session entry points
  orchestrator.py     ONE cycle end to end. Start here to understand the system
  signals/
    iv_rank.py        IV Rank, VRP, and the window-depth trust judgement
    direction.py      LightGBM classifier → calibrated P(Up)
    azte.py           rolling z-score event trigger (logged, not enforced)
  decision_schema.py  the deterministic RULEBOOK + the prompt every model sees
  guards.py           the four integrity guards. None of them calls a model
  risk_gate.py        Kelly sizing, loss caps, drawdown halt. Zero AI
  execution.py        spread construction + atomic MLEG order
  alpaca_cli.py       order submission through the Alpaca CLI, endpoint verification
  positions.py        stop-loss evaluation and closing orders
  agent_state.py      state that survives the restart between cycles
  audit_log.py        one record per cycle, pushed to GitHub
config/
  risk_limits.yaml    hard limits. Git-committed, hand-edited only, never remotely toggleable
  live_settings.json  provider, underlyings, trading mode. Remotely toggleable from /admin
docs/
  graveyard.md        every defect this agent had. Read this second
  architecture.svg    one-page diagram of a full cycle
  playbook.html       long-form architecture walkthrough
```

**If you read three files: `orchestrator.py`, `decision_schema.py`, `graveyard.md`.**

---

## 4. Two config files, and the difference matters

`config/risk_limits.yaml` holds the hard limits — max loss per trade, drawdown halt, Kelly
fraction, the adaptive-restriction threshold. It is git-committed and hand-edited only.
**It is deliberately not remotely toggleable.** Being able to change risk limits from a web
UI, even behind a password, would undermine the "the risk gate is hard-coded and not
tamperable" property the whole architecture rests on.

`config/live_settings.json` holds operational settings — which provider is live, which
underlyings are in scope, and the trading mode. This one **is** remotely toggleable.

The catch that will bite you: `live_settings.json` is fetched **from GitHub raw on `main`**,
not read from your local disk. Editing it locally does nothing until you push, and the CDN
caches it for a few minutes after that. If a change seems not to take effect, that's why.

Trading modes: `running` · `exit_only` (manages existing positions, opens nothing new) ·
`paused` (refuses everything, including exits — rarely what you want with positions open).

---

## 5. State that survives restarts

The agent is a **fresh process every tick**. Anything held in memory is gone by the next
cycle. `logs/agent_state.json` holds only what cannot be re-derived from an authoritative
source: consecutive execution failures, the circuit-breaker latch, the last cycle time, and
the per-underlying loss streak driving adaptive restriction.

Positions, equity and market hours are re-read from Alpaca every cycle and deliberately not
cached. A stored copy of something the broker already knows is a second source of truth
waiting to disagree with the first.

This is not theoretical — see graveyard entry on the circuit breaker that could never fire.

---

## 6. How it runs unattended

`.github/workflows/trading-cycle.yml`, two crons a day: 13:25 UTC with a 330-minute budget,
18:55 UTC with 90 to cover the tail. Each starts a session that drives its own 15-minute loop.
Scheduled runs pass `--live`; manual `workflow_dispatch` stays dry unless you tick the `live`
input, so smoke-testing can never reach the broker.

Secrets live in repo settings, never in the repo.

```bash
gh run list --workflow=trading-cycle.yml --limit 5
gh workflow run trading-cycle.yml -f mode=once     # safe dry smoke test
```

The workflow commits `logs/audit_log.jsonl` back to the repo after each tick, which is how the
dashboard gets fresh data. If you're working locally at the same time, expect to
`git pull --rebase` often — and don't hand-edit the audit log.

---

## 7. Sharp edges

- **Dry runs don't record IV history.** By design: one stale closed-market quote becomes the
  window's maximum and skews every subsequent rank. It also means a long dry-run stretch
  leaves the IV window frozen, which is graveyard entry 1.
- **The rulebook maps a missing `classifier_p_up` to cash, always.** Direction is the one
  signal with no fallback.
- **A missing `iv_rank` is not the same as a low one.** It withdraws the premium-selling
  branch and leaves direction intact.
- **Two models are registered but not in the cycle set** — `claude_code_cli` (no binary on the
  CI runner) and `anthropic` (org credits not spendable on the API). Both stay tested so
  re-enabling either is one name in a list. Don't "fix" this by re-adding them blindly.
- **`--test-mode` never pushes and never records history.** If you're wondering why your
  weekend run left no trace, that's why.

---

## 8. Before you change anything

1. `python -m pytest tests/ -q` — green first.
2. Make the change.
3. `python -m src.orchestrator` — one dry cycle against the live market.
4. Green tests **and** a sane dry cycle before pushing.

`tests/test_adversarial.py` is property-based and slower than the rest. Leave it in the
default run; it earns its time. It found a divide-by-zero in the risk gate on its first
execution.

The commit messages in this repo explain *why* a change was made, not what changed — the diff
already shows what. Please keep that up.
