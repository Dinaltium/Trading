---
name: Brightline
description: A read-only record of an autonomous options agent — every cycle, every model's reasoning, every refusal.
colors:
  ink: "#252525"
  paper: "#ffffff"
  instrument: "#101010"
  muted-ink: "#8e8e8e"
  rule: "#e4e4e4"
  approved: "#0ca30c"
  rejected: "#d03b3b"
  rejected-dark: "#e66767"
  bull: "#2a78d6"
  bear: "#eb6834"
  condor: "#1baf7a"
  abstain: "#898781"
typography:
  display:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.7rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.625
  numeric:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "1.75rem"
    fontWeight: 600
    fontFeature: "tabular-nums"
  label:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "11px"
    fontWeight: 500
    letterSpacing: "0.15em"
rounded:
  sm: "0.375rem"
  md: "0.5rem"
  lg: "0.625rem"
  full: "9999px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "16px"
  lg: "32px"
components:
  stat-tile:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.numeric}"
    rounded: "{rounded.lg}"
    padding: "16px"
  stat-tile-good:
    backgroundColor: "#0ca30c12"
    textColor: "{colors.approved}"
  stat-tile-critical:
    backgroundColor: "#d03b3b0f"
    textColor: "{colors.rejected}"
  verdict-approved:
    backgroundColor: "#0ca30c14"
    textColor: "{colors.approved}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  verdict-rejected:
    backgroundColor: "#d03b3b14"
    textColor: "{colors.rejected}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  strategy-badge:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "2px 10px"
  instrument-panel:
    backgroundColor: "{colors.instrument}"
    textColor: "{colors.paper}"
    rounded: "{rounded.lg}"
    padding: "32px"
---

# Design System: Brightline

## 1. Overview

**Creative North Star: "The Flight Recorder"**

An instrument that records everything and argues with nothing. Brightline's interface exists
to show what an autonomous agent did and why, including — especially — the cycles where it
did nothing. The visual system's whole job is to make a refusal as legible as a trade, and to
make it obvious at a glance which text a machine produced and which a human wrote.

The page is a white document with one dark instrument set into it. Prose is set in Geist and
reads as writing; every value a machine produced is monospaced and reads as a readout. That
split is the primary organising device, ahead of color, ahead of layout. A reader who knows
nothing about options can still tell, in one pass, which parts of this page are measurements.

What this system rejects, carried directly from PRODUCT.md's anti-references: the neon-green
candle aesthetic of trading-bot dashboards, glowing gauges, leaderboard energy, "AI-POWERED"
badges, fintech navy-and-gold trust-by-decoration, and any treatment implying the agent is
clever. The agent is *constrained*. A design that makes it look smart undercuts the claim.

**Key Characteristics:**
- One dark surface on an otherwise white page, reserved for live account state
- Machine values monospaced and tabular; human prose in Geist
- Status color only ever means state, never category or emphasis
- Reasoning shown in full, never truncated or clamped
- Flat by default: hairlines and tonal tint carry depth, not shadow

## 2. Colors

A near-achromatic document — ink on paper, one hairline gray — with saturation reserved
entirely for meaning: two status colors and three strategy identities.

### Primary
- **Ink** (`#252525`): All body copy, headings, and any value that is simply a fact. The
  default. If a color is not carrying meaning, it is this one.
- **Instrument** (`#101010`): The equity panel's ground, and nothing else on the page. See
  *The Single Instrument Rule*.

### Secondary
- **Approved Green** (`#0ca30c`): A risk-gate approval, and the count of approvals. Never
  used for "good performance", "profit", or emphasis.
- **Rejected Red** (`#d03b3b`, `#e66767` on dark): A risk-gate refusal, and the count of
  refusals. A refusal is not an error and must never be styled as one — no alert icons, no
  warning banners.

### Tertiary
Fixed categorical identity for the three tradeable structures, assigned once and never
cycled. Each appears as a 8px dot preceding the strategy name.
- **Bull Blue** (`#2a78d6`): `bull_call_spread`
- **Bear Orange** (`#eb6834`): `bear_put_spread`
- **Condor Aqua** (`#1baf7a`): `iron_condor`
- **Abstain Gray** (`#898781`): `cash`. Deliberately outside the ramp — cash is *no trade*,
  not a fourth strategy, and giving it a hue would imply parity it doesn't have.

### Neutral
- **Paper** (`#ffffff`): Page and card ground.
- **Muted Ink** (`#8e8e8e`): Labels, timestamps, secondary prose. Measured at 4.6:1 on paper
  — at the floor, not below it. Do not lighten.
- **Rule** (`#e4e4e4`): Hairline borders and dividers. 1px only.

### Named Rules

**The Single Instrument Rule.** Exactly one surface on the page is dark: the account-equity
panel. It is the instrument face — the live state of the thing being watched. No other card,
section, or container may invert. The inversion is what makes the eye land there first, and
a second dark surface destroys it.

**The Status-Is-Not-Category Rule.** Green and red mean *approved* and *rejected*. They are
forbidden as series colors, as sentiment (profit/loss), and as emphasis. A green number on
this page always means a gate let something through, never that a trade made money.

**The Meaning-Only Rule.** Saturation appears only where it carries information. A colored
element that would look the same in gray without losing meaning must be gray.

## 3. Typography

**Display / Body Font:** Geist (with `ui-sans-serif, system-ui, sans-serif`)
**Numeric / Label Font:** Geist Mono (with `ui-monospace, SFMono-Regular, monospace`)

**Character:** One family in two voices. Geist's proportional cut carries everything a person
wrote; Geist Mono carries everything a machine measured. Because they share a skeleton, the
page reads as one document rather than two pasted together — but the switch is unmistakable
at the size of a single ticker symbol.

### Hierarchy
- **Display** (600, `1.7rem`, `-0.02em`): The page title. One per page.
- **Headline** (600, `1rem`, `-0.01em`): Section headings — *Live vs. shadow*, *All trade
  cycles*. Deliberately close to body size; this is a document, not a landing page.
- **Body** (400, `0.95rem`, 1.625): Descriptions and model reasoning. Capped at `max-w-2xl`
  (~65ch).
- **Numeric** (Mono 600, `1.75rem`, tabular): Equity, cycle counts, gate tallies. Tabular
  figures are mandatory — these numbers update in place and must not jitter.
- **Label** (Mono 500, `11px`, `0.15em`, uppercase): Field labels, ticker symbols, verdict
  badges, timestamps. Tracking is what makes 11px uppercase readable; do not remove it.

### Named Rules

**The Two Voices Rule.** If a machine produced it — a price, a probability, a symbol, an IV
rank, a verdict, a timestamp — it is monospaced. If a person wrote it, it is not. There is no
third category and no exceptions for aesthetics.

**The Full Reasoning Rule.** Model justifications are never truncated, clamped, ellipsised,
or put behind a "show more". The length and the disagreement *are* the content — a page that
tidies them away has deleted the thing it exists to show.

## 4. Elevation

Flat. Depth is carried by three devices in this order: a 1px hairline (`#e4e4e4`), a tonal
background tint at 6–14% alpha, and — once, for the equity panel — full inversion to near
black. There is no shadow vocabulary. Nothing on this page floats.

This is deliberate: shadow implies a stack of movable objects, and an audit record is not
that. It is one flat sheet with things printed on it.

### Named Rules

**The Hairline Rule.** Borders are 1px. A 2px border, or a colored border used as an accent
stripe on one edge, is prohibited outright.

**The No-Ghost-Card Rule.** A 1px border and a soft wide shadow on the same element is
banned. If a surface needs separation, it gets a hairline *or* a tonal tint — never both,
and never a shadow.

## 5. Components

### Stat Tiles
- **Shape:** `0.625rem` radius, 1px hairline.
- **Neutral:** transparent ground, ink numerals.
- **Good / Critical:** the status color at 6–12% alpha as ground, full-strength as numeral.
  Used only for the approval and rejection counts.
- **Label:** uppercase mono `11px` at `0.15em`, muted ink.
- **Value:** mono `1.75rem`, semibold, tabular.

### Verdict Badges
- **Shape:** full pill, `2px 8px`.
- **Approved:** `✓ approved`, green at 14% ground.
- **Rejected:** `✕ rejected`, red at 14% ground.
- **Null:** `no trade`, muted ground, muted ink — a cycle where the gate was never reached is
  not a rejection and must not be red.
- **Accessibility:** the glyph and the word travel with the color, always. Color is never the
  sole carrier.

### Strategy Badges
- **Shape:** full pill, hairline at 10% of current color, `2px 10px`.
- **Composition:** an 8px colored dot from the fixed categorical assignment, then the label in
  mono. The dot carries identity; the text carries the name. Neither alone.

### Instrument Panel (signature)
- **Ground:** `#101010`, `0.625rem` radius, generous internal padding.
- **Contents:** the uppercase mono label, the equity figure at display scale in mono, a
  timestamp, the delta, and the sparkline in a single accent blue.
- **Rule:** one per page. See *The Single Instrument Rule*.

### Cycle Cards
- **Ground:** paper, hairline border, `0.625rem` radius.
- **Structure:** signal row (mono values under mono labels), then one block per model —
  name, execution eligibility, strategy badge, confidence, and the full reasoning as body
  prose. Gate verdict last, at the foot of the card.
- **The live model** is marked `LIVE · CAN EXECUTE`. The distinction between the model that
  can trade and the models that only watch must be visible without reading the label twice.

### Tables
- **Type:** mono throughout, tabular figures, uppercase mono column heads.
- **Density:** compact rows; this is a log, and a reader scanning it is looking for the row
  that differs from its neighbours.

## 6. Do's and Don'ts

### Do:
- **Do** monospace every machine-produced value — prices, probabilities, symbols, verdicts,
  timestamps — and set every human sentence in Geist.
- **Do** keep exactly one dark surface on the page, the equity panel.
- **Do** show model reasoning at full length, always.
- **Do** pair every status color with its word (`approved` / `rejected`) and glyph.
- **Do** use `tabular-nums` on every figure that updates in place.
- **Do** render an untrusted signal as `—` or `untrusted`, never as a number.
- **Do** state timestamps in US market time, labelled.
- **Do** treat a refusal as content. It gets the same visual weight as a trade.

### Don't:
- **Don't** render an untrusted IV Rank as `0.0`. This currently happens for DIA and IWM, and
  it reads as a broken feed rather than a working trust gate. *(open — fix before submission)*
- **Don't** render timestamps in IST on a US-market dashboard. This currently happens
  throughout, and every number on the page is harder to place because of it. *(open — fix
  before submission)*
- **Don't** use green for profit or red for loss. Those are gate verdicts here.
- **Don't** introduce a second dark surface, a shadow, or a border above 1px.
- **Don't** pair a 1px border with a wide soft shadow on the same element.
- **Don't** exceed `0.625rem` radius on a card. Pills are for badges only.
- **Don't** reach for the trading-bot register: neon-green candles, glowing gauges,
  leaderboard energy, "AI-POWERED" badges.
- **Don't** reach for fintech navy-and-gold, or trust-by-decoration of any kind.
- **Don't** use gradient text, glassmorphism, hero metrics, or an uppercase tracked eyebrow
  above every section. One kicker exists, at the top of the page; it is not a pattern.
- **Don't** style the agent as clever. It is constrained, and the interface should read that
  way.
