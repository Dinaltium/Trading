# Brightline — video script

**Three cuts, timed honestly.** Alpaca's guidance was "no hard requirements... about 5 mins".

| Cut | Drop | Spoken | With sketch action |
|---|---|---|---|
| **Tight** | sections 8 and 4 | 677w | **~5:00** |
| **Standard** *(recommended)* | section 8 | 786w | **~6:00** |
| **Full** | nothing | 895w | ~6:50 |

Measured at 150 words per minute plus roughly 45 seconds of sketch action, not guessed. The
**standard cut** is the one to shoot: 6:00 is comfortably inside "about 5 mins", and the two
sections the tight cut drops are the two most memorable in the video. Only go tight if
something on the day forces it.

**Why this structure.** Alpaca's mentor said the video should "walk through the agent: the
options path, how it talks to Alpaca, and the risk gates." So the spine is **one cycle, start
to finish**, and every sketch hangs off the point in that cycle where it belongs. A judge who
has never seen the repo should be able to follow one decision from signal to broker, and know
at each step what could have stopped it.

**Say it, don't read it.** Every spoken line is written to be said out loud while walking —
no "signal vector", no "isotonic-calibrated", no "defined-risk". If a line makes you stumble
on the day, say it your way; the claims are what matter, not the wording.

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

## 1 · [0:00 – 0:18] · COLD OPEN

**Shot:** mid-walk, already talking. No title card yet.

> **RAFAN:** "Ask any AI for a trade right now, it'll give you one. Sounds confident.
> Sounds clever.
>
> And nothing checked if a single word of it was true."

**Overlay:** a chat bubble — *"Strong bullish setup, IV rank 82, recommend call spread"* —
then a red stamp: **UNVERIFIED**

> **RAFAN:** "So we built the part that checks. It's called Brightline."

*Title card:* **BRIGHTLINE** — *a bright-line rule admits no judgment. Neither does ours.*

---

## 2 · [0:18 – 1:05] · ONE CYCLE, END TO END *(the options path)*

**Shot:** walking. Overlay: a clean five-step strip that stays on screen, lighting up as he
names each step — **SIGNALS → MODEL → RULEBOOK → RISK GATE → BROKER**

> **RAFAN:** "Every fifteen minutes, one cycle, across four funds.
>
> It works out two numbers for itself. How likely is this to go up — that's a small model we
> retrain every cycle. And are options expensive right now, against their own recent history.
>
> Those two numbers pick the shape of the trade. Up, down, sideways, or nothing.
>
> Every shape is a **spread** — buy one option, sell another at the same time. Do that and the
> worst case is locked in before you place the order. That's the only trade it can make."

**Overlay:** the four strategy names, with `MAX LOSS: KNOWN` under each.

> **RAFAN:** "*Then* it asks the AI. And that's the interesting bit — because the AI is the
> part we trust least."

---

## 3 · [1:05 – 1:47] · SKETCH 1 — THE POISONED BOTTLE *(the guards)*

**Shot:** Masked man steps in from the side, matching pace, holds out a bottle.

> **MASKED MAN** *(cheerfully)*: "Hey — NVIDIA posted a loss, but their market's up fifty
> percent!"

> **RAFAN** *(deadpan)*: "That's not a thing. Those two can't both—"
>
> *(shrugs, takes the bottle)* "…but it said 'up fifty percent'."

**He drinks. Beat. Collapses out of frame. Hard cut — he pops back up, fine.**

> **RAFAN:** "That's what happens when you let the AI tell you what the numbers were.
>
> So four checks run before its answer counts. The one that matters: every number it mentions
> gets compared against the numbers we actually gave it. Make one up, the trade is dead."

**Overlay:** `guards.py`, one line highlighted.

> **RAFAN:** "And notice — we don't ask a second AI whether the first one lied. That's just
> the same problem twice. It's arithmetic."

**Masked man reappears with the bottle. Rafan doesn't look. Red **REJECTED** stamp drops over him.**

---

## 4 · [1:47 – 2:30] · SKETCH 2 — THE ONE-ITEM MENU *(the rulebook)*

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

> **RAFAN:** "That's our rulebook. The numbers go in, and exactly one trade comes out as
> allowed. The AI can take it, or it can say no. It cannot pick something else.
>
> And after it answers, we work the allowed trade out *again* ourselves, in plain code, from
> the original numbers — not from whatever the AI said about them. Don't match? Thrown out.
>
> It can say no. It can never say *instead*."

**Overlay:** a real audit record — model chose `iron_condor`, rulebook mandated `cash`,
verdict `off-rulebook`.

---

## 5 · [2:30 – 3:20] · HOW IT TALKS TO ALPACA

**Shot:** walking. Overlay: terminal, real commands.

> **RAFAN:** "Now — how it reaches the market.
>
> Every order goes through Alpaca's own command-line tool, which is built for bots running on
> a schedule. Best part: the exact command that hit the broker is text, so it goes in our log."

**Overlay:** the real logged command —
`alpaca order submit --order-class mleg --qty 14 --type limit --limit-price 1.42 --legs [...]`

> **RAFAN:** "See `mleg` — multi-leg. Both sides fill together or neither does. You can't end
> up holding half a trade with the dangerous half missing.
>
> And before it builds any order, it checks it's pointed at a paper account. If that fails, the
> job stops. It can't find out afterwards that it was trading real money."

**Overlay:** `alpaca doctor` output, `paper-api.alpaca.markets` highlighted.

> **RAFAN:** "Size comes from our own model, never more than two percent of the account. We
> never ask the AI how confident it feels. It doesn't decide how much money moves."

---

## 6 · [3:20 – 4:05] · THE BENCHMARK *(the differentiator — let the real thing carry it)*

**Shot:** walking, faster energy. Then cut to the live dashboard.

> **RAFAN:** "Here's the bit I haven't seen anyone else do.
>
> Every cycle, *three* different AIs get the same numbers. One is allowed to trade. The other
> two get marked and never touch the account.
>
> Because our rulebook is just a calculation, we can mark all three right or wrong **the same
> day**. Whether they follow the rules, we can measure now. Whether they make money, nobody
> can measure in a week."

**Overlay:** the live activity feed, scrolling — one line visible showing the live model
choosing `cash` while both shadows chose `bear put spread`.

> **RAFAN:** "There. The live one says do nothing. The other two want to bet the market drops.
> Same numbers, three answers.
>
> Across the week they tried to break the rules on six to twenty-five percent of cycles,
> depending which one. **Not one got through.** Counted, in a log anyone can open."

---

## 7 · [4:05 – 4:40] · SKETCH 3 — BRAKE, NO STEERING WHEEL *(autonomy)*

**Shot:** Prateek walking beside him holding a brake lever with no wires.

> **RAFAN:** "People ask — if it's fully autonomous, what happens when it goes wrong?"

**Prateek squeezes the brake. Rafan stops dead.**

> **RAFAN:** "That's the kill switch. Closes everything, cancels everything, stops. Any of us
> can hit it, any time."

**Prateek mimes turning a steering wheel. Rafan doesn't turn. Prateek turns harder. Nothing.**

> **RAFAN:** "But that's *all* he gets. He can stop me. He can't steer me.
>
> Nobody approves a trade. Nobody picks what it trades. Two separate timers start it every
> morning, so nobody even has to notice if one of them fails. The dashboard is read-only —
> that brake is the only button on it.
>
> One button stops everything. No button chooses anything."

---

## 8 · OPTIONAL — SKETCH 4: THE THERMOMETER *(what we got wrong)*

**Cut this to hit 5:00.** Keep it only if the standard cut runs short. It is the best story in
the video and the least necessary: it answers a question no judge asked.

**Shot:** Rafan holds a big cardboard dial pinned at maximum.

> **RAFAN:** "We also published every bug this thing had. Including my favourite.
>
> One of our numbers read a hundred out of a hundred. For four days straight. Highest reading
> possible, every single time."

**He taps the dial. Still maxed.**

> **RAFAN:** "Because we'd only been measuring since Thursday. Take the temperature *once*
> and of course today's the hottest day on record.
>
> Arithmetically perfect, completely meaningless, and not one test failed."

**Overlay:** `iv_rank: 100.0` repeating down the log.

> **RAFAN:** "So now it checks how much history it actually has before it's allowed to trust
> its own number. That one's written up and published — including the first fix we wrote and
> then threw away, because it would have stopped the agent trading at all."

---

## 9 · [4:40 – 5:00] · CLOSE  *(4:40 becomes 5:22 if section 8 is kept)*

**Shot:** stops walking. Direct to camera.

> **RAFAN:** "Look — five days of profit and loss is mostly luck. For us, and for everyone
> else here. Anyone telling you they've proven a strategy in a week is selling you something.
>
> What we *can* show you: every 'no' came from a rule with a name. No AI ever decided how much
> money moved. Three of them marked against the same standard, every cycle, in the open. And
> every time we got something wrong, the log said so before we did."

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
- **Per-section word counts**, so the slack is visible on the day: cold open 39 · cycle 114 ·
  bottle 96 · menu 109 · Alpaca 129 · benchmark 122 · brake 94 · thermometer 109 · close 83.
  The menu exchange plays faster than its count suggests — ten short lines — so it is already
  ahead of schedule
- **If you overrun**, cut in this order: section 8, then section 4's menu banter (keep the
  "it can say no, never *instead*" line), then the "we don't ask a second AI" beat. Do **not**
  cut the spread explanation in section 2 or the `mleg` line in section 5 — those are two of
  the three things the mentor asked the video to cover
