# Brightline

> A bright-line rule admits no judgment. Neither does ours.

## Register

**Product.** The dashboard is a read-only operational surface — equity series, cycle
tables, per-model reasoning, gate verdicts. Design serves the data. It is also the page
judges land on, so it has to be legible on first read by someone who has never seen the
system, but that argues for clarity, not for a hero.

## What this is

An autonomous options-trading agent on Alpaca paper. Every 15 minutes it computes a signal
vector, asks three language models the same question, and lets exactly one of them reach the
broker — behind a deterministic rulebook and risk gate that the model cannot argue with.

The design claim in one line: **the model has discretion to decline, never to substitute.**

Three models receive an identical signal vector each cycle. One executes; the other two are
recorded as a shadow benchmark. Because the rulebook is a pure function of the same signals,
every answer is markable right or wrong immediately, without waiting weeks for P&L. That is
the measurement the whole architecture exists to produce.

## Users

- **Judges and reviewers** (primary, this week). Arrive cold, have minutes, need to see the
  thesis demonstrated rather than asserted. The shadow comparison and the refusal record are
  what they came for.
- **The operator** (Rafan, Prateek). Needs to answer "is it running, what did it do, why did
  it refuse" without opening a terminal, and to stop it from a phone.
- **Engineers reading it later.** The audit log and the graveyard doc are for them.

## Brand personality

**Exacting. Plain-spoken. Unflattering to itself.**

The project's credibility comes from stating limits rather than hiding them — the graveyard
document, the "still open" section, the refusal to claim edge from five days of P&L. The
interface should carry the same register: numbers stated, reasoning shown in full, nothing
truncated to look tidier than it is.

## Anti-references

- **Trading-bot dashboards.** Neon green candles, glowing gauges, leaderboard energy,
  "AI-POWERED" badges. The aesthetic of a product selling certainty.
- **Fintech navy-and-gold.** Trust-by-decoration.
- **Any framing that implies the agent is smart.** The agent is constrained. That is the
  point, and the design should not undercut it.
- Hero metrics, gradient text, glassmorphism, marketing eyebrows over every section.

## Design principles

1. **Show the refusal.** Rejections are first-class content, not error states. A cycle where
   nothing traded is as informative as one where something did, and the gate's stated reason
   is the most valuable string on the page.
2. **Never truncate reasoning.** Each model's full justification is shown. Truncating it
   would hide exactly the disagreement the project measures.
3. **Monospace for anything a machine produced** — prices, probabilities, symbols, verdicts.
   Prose typeface for anything a human wrote. The reader should be able to tell which is
   which without being told.
4. **Untrusted is not zero.** A signal that failed its trust gate must never render as
   `0.0`. Displaying an absent number as a real one is the single worst thing this interface
   can do.
5. **Timestamps in market time.** The market is American; the operator is not. Ambiguity here
   makes every other number harder to read.

## Accessibility

Body text ≥ 4.5:1. The green/red verdict colours must never be the only carrier of meaning —
the word (`approved` / `rejected`) travels with the colour everywhere it appears.

## Constraints

- Read-only by construction. The dashboard cannot place, modify, or cancel an order. The one
  write it exposes is the operator kill switch, behind a password, and it can only ever make
  the agent do less.
- Data comes from `logs/audit_log.jsonl` in the repo, committed by the runner each cycle.
  The page is a view over the audit trail, never a second source of truth.
