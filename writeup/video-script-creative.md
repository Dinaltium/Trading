# Video script — walking explainer with sketches

Format: walk-and-talk to camera, quick cuts, thumbnails and screen-grabs popping in beside
the presenter, physical sketches acting out each mechanism. Roughly **3:00**.

**The rule that makes this work:** every sketch dramatizes something that genuinely exists in
the repo. The bottle is Guard 2. The menu is the rulebook. The brake is `/admin`. If a judge
opens the code after watching, each gag has a real line behind it. Metaphor is fine; a sketch
for a feature you don't have is not.

**Never on screen:** invented P&L, fake trades, mocked dashboards, or the API key panel.

---

## Cast & props

| | |
|---|---|
| **Rafan** | on camera, walking — plays "the agent" in sketches |
| **Prateek** | the masked man, the waiter, the hand on the brake |
| Props | water bottle, a one-item menu, a thermometer or a big cardboard dial, a red button or a bike brake lever |
| Wardrobe | masked man in a hoodie + mask. Same hoodie every time he appears — he becomes a running character |

---

## [0:00 – 0:12] · COLD OPEN — no intro, straight in

**Shot:** mid-walk, already talking. No title card yet.

> **RAFAN:** "If you ask an AI for a trade right now, it'll give you one. Confident. Cites
> the Greeks. Sounds *brilliant.*
>
> And absolutely nothing checked whether any of it was true."

**Overlay:** a chat bubble mock — *"Strong bullish setup, IV rank 82, recommend call spread"* —
then a red stamp across it: **UNVERIFIED**

*Title card slams in over the walk:* **{{NAME}}**

---

## [0:12 – 0:50] · SKETCH 1 — THE POISONED BOTTLE *(guards)*

**Shot:** Rafan walking. Masked man steps in from the side, matching pace, holds out a bottle.

> **RAFAN:** "Everyone's building autonomous trading agents. Almost nobody's building the
> part that assumes the agent is being *lied to*."

> **MASKED MAN** *(cheerfully)*: "Hey — NVIDIA posted a loss, but their market's up fifty
> percent!"

> **RAFAN** *(to camera, deadpan)*: "That's not a thing. Those two can't both—"
>
> *(shrugs, takes the bottle)* "…but it said 'up fifty percent'."

**He drinks. Beat. He collapses out of frame.**

**Overlay:** equity curve falling off a cliff — hand-drawn, obviously stylised, **not** a real
chart.

**Hard cut. Rafan pops back up, completely fine, brushing himself off.**

> **RAFAN:** "So that's what happens when the model gets to report its own inputs.
>
> Here's what actually happens in ours."

**Overlay:** `guards.py` on screen, one line highlighted

> **RAFAN:** "Guard two. Every number the model quotes in its reasoning gets checked against
> the numbers we actually handed it. Quote a figure you were never given — the trade dies
> before it exists.
>
> The guard doesn't ask an AI whether the AI is lying. That'd be a bit circular."

**Masked man reappears behind him, offers the bottle again. Rafan doesn't even look. A big
red `REJECTED` stamp drops over the masked man.**

---

## [0:50 – 1:25] · SKETCH 2 — THE ONE-ITEM MENU *(the rulebook)*

**Shot:** Rafan sits at a table. Prateek as waiter, hands over a menu.

> **RAFAN:** "Okay so, what can I have?"

**Close-up on the menu. One item. Nothing else.**

> **PRATEEK:** "Bear put spread."

> **RAFAN:** "What if I want an iron condor?"

> **PRATEEK:** "No."

> **RAFAN:** "What if I'm *really confident*—"

> **PRATEEK:** "No."

> **RAFAN:** "…Can I have nothing?"

> **PRATEEK** *(nods)*: "You can always have nothing."

**Cut to walking.**

> **RAFAN:** "That's the rulebook. Signals go in, and exactly one strategy is permitted. The
> model can take it, or it can decline. It cannot invent a third option.
>
> And here's the bit that matters — after the model answers, we work out the mandated
> strategy *again*, in plain Python, from the raw numbers. Not from the model's summary of
> the numbers. If they don't match, it's rejected.
>
> Discretion to decline. Never to substitute."

**Overlay:** real audit record — model chose `iron_condor`, rulebook mandated `cash`,
verdict `off-rulebook`. That's a genuine line from the log.

---

## [1:25 – 1:50] · THE BENCHMARK *(no sketch — let the real thing carry it)*

**Shot:** walking, faster energy.

> **RAFAN:** "Now the part I haven't seen anyone else do.
>
> Every fifteen minutes, *three* different AI models get the exact same signals. One of them
> trades. The other two shadow it — they never touch the account. And all three get scored
> against that same rulebook, every cycle.
>
> So 'which model actually follows the rules' isn't our opinion. It's counted. In a public
> log. Here—"

**Overlay:** the real 16:53 cycle — Groq `bear_put_spread`, Featherless `bear_put_spread`,
Mistral `cash`.

> **RAFAN:** "Two agreed. The third refused. All three on record. That's data nobody in this
> hackathon has, because nobody else is running the comparison."

---

## [1:50 – 2:15] · SKETCH 3 — BRAKE, NO STEERING WHEEL *(the autonomy boundary)*

**Shot:** Rafan walking. Prateek walking beside him holding a brake lever with no wires — or
a big red button on a board.

> **RAFAN:** "People ask: if it's fully autonomous, what happens when it goes wrong?"

**Prateek squeezes the brake. Rafan stops dead mid-stride.**

> **RAFAN:** "That's flatten. Closes every position, cancels every resting order, stops. One
> action, and a human can hit it any time."

**Prateek then mimes turning a steering wheel. Rafan does not turn. He keeps walking straight.
Prateek turns harder. Nothing.**

> **RAFAN:** "But that's all he gets. He can stop me. He *cannot* steer me.
>
> Some agents in this competition ask a human to approve every single order. That's not an
> autonomous agent, that's a person trading with extra steps.
>
> One action stops everything. No action picks anything."

---

## [2:15 – 2:45] · SKETCH 4 — THE THERMOMETER *(the graveyard)*

**Shot:** Rafan holds a thermometer / big cardboard dial pinned at maximum.

> **RAFAN:** "We also published every bug this thing had. Including my favourite.
>
> Our volatility signal read *one hundred out of one hundred*. For four days straight.
> Hottest reading possible, every single cycle."

**He taps the dial. Still maxed.**

> **RAFAN:** "Because we'd only been measuring since Thursday afternoon.
>
> If you've only ever taken the temperature *once*, of course today's the hottest day on
> record. The number was arithmetically perfect and completely meaningless. It sent
> forty-seven cycles out of forty-seven to cash."

**Overlay:** `iv_rank: 100.0` repeating down the audit log.

> **RAFAN:** "Not one test failed. For four days.
>
> So now the agent checks how *deep* its history is before it's allowed to trust its own
> number. And that bug is written up, published, with the fix we tried first and threw away."

---

## [2:45 – 3:00] · CLOSE

**Shot:** stops walking. Direct to camera.

> **RAFAN:** "Look — five days of profit and loss is mostly noise. For us and for everyone
> else here. Anyone claiming they've proven a strategy in a week is selling you something.
>
> What we can show you: every refusal traces back to a named rule. No model ever sized a
> position. And every time we got it wrong, the log says so."

**Beat. Masked man leans into frame with the bottle one last time.**

> **RAFAN** *(without looking)*: "No."

**Cut to black.**

**End card:** `{{NAME}}` · dashboard URL · repo URL · Team AAF11

---

## Shot list

| # | Shot | Location | Props |
|---|---|---|---|
| 1 | Cold open walk | street | — |
| 2 | Bottle handoff + collapse | wide, street | bottle, mask, hoodie |
| 3 | Pop back up | same spot | — |
| 4 | Menu scene | table/café | one-item menu |
| 5 | Benchmark walk | street | — |
| 6 | Brake + steering | walking, two-shot | brake lever / red button |
| 7 | Thermometer | walking or static | dial prop |
| 8 | Close + final "No." | anywhere clean | bottle |

**Screen-recordings needed:** `guards.py`, one real audit record showing `off-rulebook`, the
16:53 three-model disagreement, `iv_rank: 100.0` repeating, `/admin` with the four modes.

## Production notes

- **Subtitles burned in** — agreed Aug 30, and most people watch muted
- **Phone audio, not laptop mic.** Phone in a pocket close to the speaker beats a distant
  camera mic every time
- Shoot the walking shots in one direction with consistent light; cuts hide everything else
- The masked man never speaks after the first line. He just keeps offering the bottle. Recurring
  gag, zero extra script
- Overlays should look deliberately hand-drawn where they're metaphors, and be pixel-accurate
  screenshots where they're evidence. **Never blur that line**
- **Blur or crop the Alpaca API key panel** if the dashboard is on screen
- Say **three models**, not four. The log shows three

---

# Poster / cover image — 16:9, PNG or JPG

## Design direction

The submission list is a wall of thumbnails. At 200px wide, screenshots turn to mush and
gradients look like every other AI-generated cover. **Typography wins at thumbnail size.**

Three teams in this track named themselves some variant of Aegis and their covers all look
like security software. Go the other way: make it look like a **terminal**, a **legal
document**, or a **lab notebook** — quiet, precise, deliberate.

The one idea to carry: **the model may decline, it can never invent.**

## Prompt A — terminal / audit log *(recommended)*

> A 16:9 minimalist poster in the style of a dark terminal window. Deep near-black background
> (#0d0d0f) with a subtle fine grid. Centred, large monospace wordmark reading `{{NAME}}` in
> warm off-white. Directly beneath, in smaller muted grey monospace: "the model may decline a
> trade. it can never invent one." To the left edge, a faint vertical column of dim monospace
> log lines suggesting an audit trail, mostly illegible, one line highlighted in amber. Thin
> amber accent rule under the wordmark. Enormous negative space. No charts, no candlesticks,
> no robots, no glowing brains, no stock imagery. Flat, print-like, high contrast, editorial.

## Prompt B — the one-item menu

> A 16:9 poster photographed from directly above: a plain cream restaurant menu card on a
> dark walnut table, shot in soft natural light. The menu has a single line of elegant
> serif text and nothing else. Enormous white space on the card. Beside it, a folded note
> in monospace reading `{{NAME}}`. Muted, editorial, film-still quality, shallow depth of
> field. No people, no hands, no logos, no charts.

## Prompt C — the pinned dial *(the graveyard idea)*

> A 16:9 editorial poster: a single analogue gauge, needle pinned hard at maximum, isolated
> on a deep charcoal background with dramatic side lighting. Brass and glass, scientific
> instrument, slightly worn. Bottom-left in small monospace: `{{NAME}}`. Minimal, moody,
> high contrast, lots of empty space. No text on the dial face, no charts, no digital UI.

## Practical

**Generate the image, then add the text yourself in Canva or Figma.** Image models mangle
typography — you'll get `{{NAME}}` rendered as `NAMME` or worse, and it'll be the first thing
a judge sees. Ask for the composition with space left for text, then set the type properly.

- Export at **1920×1080**, PNG or JPG
- Test it at **200px wide**. If the name isn't instantly readable, make it bigger
- Whatever you pick, the same wordmark goes on the deck title slide, the video end card,
  and the Day 5 naming post
