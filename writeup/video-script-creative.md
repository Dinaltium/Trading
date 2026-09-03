# Brightline — video script

**Length: 5:00.** Walk-and-talk to camera, quick cuts, screen-grabs beside the presenter,
physical sketches acting out each mechanism.

**Why this structure.** Alpaca's mentor said the video should "walk through the agent: the
options path, how it talks to Alpaca, and the risk gates." So the spine is **one cycle, start
to finish**, and every sketch hangs off the point in that cycle where it belongs. A judge who
has never seen the repo should be able to follow the path of a single decision from signal to
broker, and know at each step what could have stopped it.

**The rule that makes this work:** every sketch dramatises something that genuinely exists in
the repo. The bottle is Guard 2. The menu is the rulebook. The brake is the kill switch. If a
judge opens the code after watching, each gag has a real line behind it. Metaphor is fine; a
sketch for a feature you don't have is not.

**Never on screen:** invented P&L, fake trades, mocked dashboards, or the Alpaca API key
panel on the dashboard's right-hand side.

---

## Cast & props

| | |
|---|---|
| **Rafan** | on camera, walking — plays "the agent" in sketches |
| **Prateek** | the masked man, the waiter, the hand on the brake |
| Props | water bottle, a one-item menu, a big cardboard dial, a bike brake lever |
| Wardrobe | masked man in a hoodie + mask. Same hoodie every time — he becomes a running character |

---

## [0:00 – 0:18] · COLD OPEN

**Shot:** mid-walk, already talking. No title card yet.

> **RAFAN:** "Ask any AI for a trade right now and it'll give you one. Confident. Cites the
> Greeks. Sounds brilliant.
>
> And nothing checked whether a single word of it was true."

**Overlay:** a chat bubble — *"Strong bullish setup, IV rank 82, recommend call spread"* —
then a red stamp: **UNVERIFIED**

> **RAFAN:** "We built the part that checks. It's called Brightline."

*Title card:* **BRIGHTLINE** — *a bright-line rule admits no judgment. Neither does ours.*

---

## [0:18 – 1:00] · ONE CYCLE, END TO END *(the options path)*

**Shot:** walking. Overlay: a clean five-step strip that stays on screen, lighting up as he
names each step — **SIGNALS → MODEL → RULEBOOK → RISK GATE → BROKER**

> **RAFAN:** "Every fifteen minutes the agent runs one cycle, on four index ETFs — SPY, QQQ,
> IWM, DIA.
>
> First it builds the signals itself. A LightGBM classifier, retrained from scratch every
> cycle on nine hundred days of bars, gives a probability that the underlying rises. Separately
> we compute implied-volatility rank from our own recorded history.
>
> Those two numbers pick the structure. Bullish enough — a bull call spread. Bearish enough —
> a bear put. Neutral *and* volatility is expensive — an iron condor. Nothing clean — cash.
>
> Every one of those is a **defined-risk spread**. Two legs or four, bought and sold together.
> The maximum loss is known before the order exists. That's the entire options universe this
> agent is allowed to touch — no naked options, no single legs, no assignment risk."

**Overlay:** the four strategy names, with `MAX LOSS: KNOWN` under each.

> **RAFAN:** "Then the model gets asked. And this is where it gets interesting, because the
> model is the *least* trusted component in the system."

---

## [1:00 – 1:40] · SKETCH 1 — THE POISONED BOTTLE *(the guards)*

**Shot:** Masked man steps in from the side, matching pace, holds out a bottle.

> **MASKED MAN** *(cheerfully)*: "Hey — NVIDIA posted a loss, but their market's up fifty
> percent!"

> **RAFAN** *(deadpan)*: "That's not a thing. Those two can't both—"
>
> *(shrugs, takes the bottle)* "…but it said 'up fifty percent'."

**He drinks. Beat. Collapses out of frame. Hard cut — he pops back up, fine.**

> **RAFAN:** "That's what happens when a model gets to report its own inputs.
>
> So before any answer is allowed to count, four guards run. The important one: every number
> the model quotes in its reasoning is checked against the numbers we actually handed it.
> Quote a figure you were never given, and the trade dies before it exists."

**Overlay:** `guards.py`, one line highlighted.

> **RAFAN:** "Note what that guard is *not*. It doesn't ask another AI whether the first AI
> was lying. That'd be circular. It's arithmetic."

**Masked man reappears with the bottle. Rafan doesn't look. Red **REJECTED** stamp drops over him.**

---

## [1:40 – 2:20] · SKETCH 2 — THE ONE-ITEM MENU *(the rulebook)*

**Shot:** Rafan at a table. Prateek as waiter hands over a menu.

> **RAFAN:** "What can I have?"

**Close-up: one item. Nothing else.**

> **PRATEEK:** "Bear put spread."
> **RAFAN:** "What if I want an iron condor?"
> **PRATEEK:** "No."
> **RAFAN:** "What if I'm *really confident*—"
> **PRATEEK:** "No."
> **RAFAN:** "…Can I have nothing?"
> **PRATEEK** *(nods)*: "You can always have nothing."

**Cut to walking.**

> **RAFAN:** "Signals go in, and exactly one strategy is permitted. The model can take it, or
> decline. It cannot invent a third option.
>
> And after it answers, we recompute the mandated strategy *again*, in plain Python, from the
> raw numbers — not from the model's summary of them. If they don't match, rejected.
>
> Discretion to decline. Never to substitute."

**Overlay:** a real audit record — model chose `iron_condor`, rulebook mandated `cash`,
verdict `off-rulebook`.

---

## [2:20 – 2:55] · HOW IT TALKS TO ALPACA

**Shot:** walking. Overlay: terminal, real commands.

> **RAFAN:** "Now the part that actually reaches the market.
>
> We don't use an SDK. Every order goes through Alpaca's own CLI, shelled out to as a
> subprocess. Two reasons. It's built for long-running agent sessions and cron jobs — which is
> exactly what this is. And it means the exact command that hit the broker is a string we can
> print into the audit log, verbatim."

**Overlay:** the real logged command —
`alpaca order submit --order-class mleg --qty 14 --type limit --limit-price 1.42 --legs [...]`

> **RAFAN:** "That's a multi-leg order. `mleg`. All legs fill together or none do — you can
> never end up with half a spread and unlimited risk on the other side.
>
> And before any order is built, one more thing runs: `alpaca doctor`. Out of process. It
> resolves the endpoint and confirms it's paper. If that check fails, the job dies. The agent
> is not capable of discovering it's pointed at a live account after the fact."

**Overlay:** `alpaca doctor` output, `paper-api.alpaca.markets` highlighted.

> **RAFAN:** "Sizing is quarter-Kelly, off the classifier's calibrated probability, capped at
> two percent of equity per trade. The model is never asked how confident it is. It doesn't
> size anything."

---

## [2:55 – 3:35] · THE BENCHMARK *(the differentiator — let the real thing carry it)*

**Shot:** walking, faster energy. Then cut to the live dashboard.

> **RAFAN:** "Here's the part I haven't seen anyone else do.
>
> Every cycle, *three different AI models* get the exact same signal vector. One of them can
> trade. The other two are recorded and scored, and never touch the account.
>
> Because the rulebook is a pure function of those same signals, every answer can be marked
> right or wrong **immediately** — you don't wait weeks for P&L to tell you. Compliance is
> measurable today. Profit isn't."

**Overlay:** the live activity feed, scrolling — one line visible showing the live model
choosing `cash` while both shadows chose `bear put spread`.

> **RAFAN:** "There it is. Live model says cash, both shadows say bear put spread. Same
> inputs, three answers.
>
> Across the run, the models tried to go off-book on between six and twenty-five percent of
> cycles depending which model. **None of those ever reached the broker.** Not our opinion —
> it's counted, in a public log, in the repo."

---

## [3:35 – 4:05] · SKETCH 3 — BRAKE, NO STEERING WHEEL *(autonomy)*

**Shot:** Prateek walking beside him holding a brake lever with no wires.

> **RAFAN:** "People ask — if it's fully autonomous, what happens when it goes wrong?"

**Prateek squeezes the brake. Rafan stops dead.**

> **RAFAN:** "That's the kill switch. Closes every position, cancels every resting order,
> stops. A human can hit it any time."

**Prateek mimes turning a steering wheel. Rafan doesn't turn. Prateek turns harder. Nothing.**

> **RAFAN:** "But that's *all* he gets. He can stop me. He cannot steer me.
>
> Nobody approves a trade. Nobody picks an underlying. Two independent schedulers start the
> sessions, so a human never has to notice a missed trigger. The dashboard is read-only —
> the one write it exposes is that brake.
>
> One action stops everything. No action picks anything."

---

## [4:05 – 4:35] · SKETCH 4 — THE THERMOMETER *(what we got wrong)*

**Shot:** Rafan holds a big cardboard dial pinned at maximum.

> **RAFAN:** "We also published every bug this thing had. Including my favourite.
>
> Our volatility signal read a hundred out of a hundred. For four days. Hottest possible
> reading, every single cycle."

**He taps the dial. Still maxed.**

> **RAFAN:** "Because we'd only been measuring since Thursday afternoon. If you've taken the
> temperature *once*, of course today's the hottest day on record.
>
> Arithmetically perfect. Completely meaningless. Not one test failed, for four days."

**Overlay:** `iv_rank: 100.0` repeating down the log.

> **RAFAN:** "Now the agent checks how deep its own history is before it's allowed to trust
> its own number. That bug is written up and published — including the first fix we wrote and
> threw away, because it would have stopped all trading."

---

## [4:35 – 5:00] · CLOSE

**Shot:** stops walking. Direct to camera.

> **RAFAN:** "Five days of profit and loss is mostly noise — for us and for everyone else
> here. Anyone claiming they've proven a strategy in a week is selling you something.
>
> What we *can* show you: every refusal traces to a named rule. No language model ever sized a
> position or reached the broker unchecked. Three models scored against the same standard,
> every cycle, in public. And every time we got it wrong, the log says so first."

**Beat. Masked man leans in with the bottle one last time.**

> **RAFAN** *(without looking)*: "No."

**Cut to black.**

**End card:** **BRIGHTLINE** · dashboard URL · repo URL · Team AAF11 · Alpaca paper account `PA3LKGJM8E2F`

---

## Shot list

| # | Shot | Location | Props |
|---|---|---|---|
| 1 | Cold open walk | street | — |
| 2 | Cycle walkthrough | street | — |
| 3 | Bottle handoff + collapse | wide, street | bottle, mask, hoodie |
| 4 | Pop back up + REJECTED stamp | same spot | bottle |
| 5 | Menu scene | table/café | one-item menu |
| 6 | Alpaca / CLI walk | street | — |
| 7 | Benchmark walk + dashboard | street | — |
| 8 | Brake + steering | walking two-shot | brake lever |
| 9 | Thermometer | walking or static | dial prop |
| 10 | Close + final "No." | anywhere clean | bottle |

**Screen-recordings needed** — all real, none mocked:

1. `guards.py` with the faithfulness guard highlighted
2. One audit record showing `off-rulebook`
3. The **activity feed** scrolling, framed on a cycle where the live model and shadows disagree
4. The real `alpaca order submit --order-class mleg …` line from the audit log
5. `alpaca doctor` resolving to `paper-api.alpaca.markets`
6. `iv_rank: 100.0` repeating down the log
7. The kill switch page showing its four modes

## Production notes

- **Subtitles burned in** — most judges watch muted, and this script is dense
- **Phone audio, not laptop mic.** Phone in a pocket near the speaker beats a camera mic
- Shoot walking shots in one direction with consistent light; cuts hide everything else
- The masked man never speaks after the first line. He just keeps offering the bottle
- Overlays: deliberately hand-drawn where they're metaphors, pixel-accurate screenshots where
  they're evidence. **Never blur that line**
- **Crop the Alpaca API key panel** out of any dashboard capture
- Say **three models**, not four
- Pace check: this is ~700 spoken words. If a section runs long, the thermometer sketch is the
  one to trim — it's the only one that isn't load-bearing for the mentor's three questions
