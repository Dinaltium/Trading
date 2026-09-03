import { NextResponse } from "next/server";
import { getAuditRecords } from "@/lib/audit";
import { buildSummary, daysRunning, INCEPTION_EQUITY } from "@/lib/summary";
import { verifyBriefing } from "@/lib/verify-briefing";

// A briefing written by the live model, on demand.
//
// The single rule this route exists to enforce: the model receives figures that have already
// been computed and is asked to explain them. It never sees the audit log, never adds, never
// divides, and is told in the system prompt that inventing a number is the one unrecoverable
// error. That keeps the guarantee the rest of the page makes — every number on this dashboard
// is derived from the record — while still letting a model do the thing models are good at,
// which is saying what a set of numbers means to someone who has never seen them.
//
// It also means there is no prompt-injection surface. The models' free-text reasoning is the
// only attacker-influenced content in the log, and none of it is passed here; the payload is
// numbers and fixed labels this file constructs.

export const dynamic = "force-dynamic";

// Featherless, not the live trading provider. The briefing is commentary, not execution, and
// having it written by a model that cannot reach the broker makes that separation visible:
// the model narrating the account is structurally incapable of acting on it.
//
// Qwen2.5-7B-Instruct, not the Qwen3.5-9B the shadow benchmark uses. 3.5 is a reasoning
// model and spends its budget there rather than on the answer: measured at ~5,600 reasoning
// tokens and an EMPTY reply against this prompt at a 4,000-token cap, ~39s when it did
// answer, and "/no_think" does not suppress it. 2.5-Instruct returns the same content in 8
// seconds with no reasoning pass at all. A briefing nobody waits for is a briefing nobody
// reads, and this one is behind a button a judge presses.
const API_URL = "https://api.featherless.ai/v1/chat/completions";
const API_KEY_ENV = "FEATHER_API_KEY";
const MODEL = "Qwen/Qwen2.5-7B-Instruct";
const MAX_TOKENS = 900;
const REQUEST_TIMEOUT_MS = 40_000;
const TOTAL_BUDGET_MS = 90_000;

const SYSTEM = `You are explaining an autonomous options-trading agent's current state to a
visitor who has never seen it before and may not trade options.

You will be given figures that have ALREADY been computed from the agent's audit log.

Rules, in order of importance:
1. Never state a number that is not in the data given to you. Do not add, subtract, average,
   or infer any figure. Inventing a number is the one unrecoverable error here.
2. Do not predict, forecast, or advise. No view on where the market goes.
3. Do not claim the strategy is working or failing. A few days of P&L is not evidence either
   way, and saying so plainly is better than a verdict.
4. Explain what the numbers mean, especially the refusals — the agent's discretion is the
   discretion to decline, never to substitute a trade the rulebook did not mandate.
5. gate_approved and gate_refused sum to gate_verdicts_total. That total is NOT the same
   population as proposals_this_session, because the gate also rules on cycles the model sat
   out. Never write that refusals are "the remaining" or "the other" of the proposals, and
   never subtract one from the other — the two counts do not reconcile and saying they do is
   an invented number.
6. The three models are language models being compared, not forecasting models. Exactly one
   of them can execute; the other two are recorded and scored and NEVER influence the gate,
   the sizing, or any order. Do not write that their agreement or disagreement feeds the
   gate's verdict — it does not, and that is the point of recording them.
7. strategy_mix counts what the live model PROPOSED in the latest session. It is not a list
   of open positions and must never be described as what the agent currently holds.
8. The figures describe latest_session_date, which is the most recent session with data. Call
   it "today" ONLY if latest_session_is_today is true. Otherwise say "its most recent
   session" or name the date. Markets are shut for most of the clock, so the latest session
   is usually not today, and writing otherwise states something false.

Three short paragraphs, plain prose, no headings, no bullet points, no markdown. Around 130
words. Address the reader directly. Be plain, not promotional.`;

// One briefing per state of the log. Repeated clicks on an unchanged page cost nothing, and
// a public endpoint that bills per press is a bad idea on a URL anyone can open.
let cache: { key: string; text: string; at: number; checked: number } | null = null;

export async function GET() {
  const key = process.env[API_KEY_ENV];
  if (!key) {
    return NextResponse.json(
      { error: `No ${API_KEY_ENV} configured on this deployment.` },
      { status: 503 }
    );
  }

  let facts;
  try {
    const records = await getAuditRecords();
    const s = buildSummary(records);
    if (!s || s.equityNow == null) {
      return NextResponse.json({ error: "No cycles logged yet." }, { status: 503 });
    }
    facts = {
      days_running: daysRunning(s.firstSeen),
      total_cycles: s.totalCycles,
      // Named "latest_session", never "today". Handed a key called session_date, the model
      // wrote "Today is September 2, 2026" at 05:49 UTC on September 3 — the figure was
      // right and the word was wrong, and that is the field name's fault rather than the
      // model's.
      latest_session_date: s.sessionLabel,
      today_in_market_time: s.todayInMarketTime,
      latest_session_is_today: s.latestSessionIsToday,
      cycles_in_latest_session: s.cyclesToday,
      underlyings: s.underlyings,
      equity_now: s.equityNow,
      equity_at_session_open: s.equityOpen,
      equity_at_inception: INCEPTION_EQUITY,
      change_since_inception: s.equityNow - INCEPTION_EQUITY,
      pct_since_inception: +(((s.equityNow - INCEPTION_EQUITY) / INCEPTION_EQUITY) * 100).toFixed(2),
      all_time_high: s.peak,
      all_time_low: s.trough,
      proposals_in_latest_session: s.proposed,
      gate_verdicts_total: s.approved + s.refused,
      gate_approved: s.approved,
      gate_refused: s.refused,
      most_common_refusal: s.topRefusal?.reason ?? null,
      most_common_refusal_count: s.topRefusal?.count ?? null,
      orders_reaching_broker: s.submitted,
      strategy_mix: s.strategyMix,
      models_compared: 3,
      cycles_where_models_disagreed: s.disagreedToday,
      cycles_scored: s.scoredToday,
    };
  } catch {
    return NextResponse.json({ error: "Could not read the audit log." }, { status: 502 });
  }

  const cacheKey = JSON.stringify(facts);
  if (cache && cache.key === cacheKey) {
    return NextResponse.json({
      text: cache.text,
      model: MODEL,
      cached: true,
      at: cache.at,
      figuresChecked: cache.checked,
    });
  }

  // Two attempts, then closed. The second is told exactly which figures failed, because a
  // model that invented one number will usually not invent the same one twice when shown it.
  let lastFailure: string[] = [];
  const deadline = Date.now() + TOTAL_BUDGET_MS;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    // A second attempt is only worth having if there is time left to serve it.
    if (attempt > 0 && Date.now() > deadline - REQUEST_TIMEOUT_MS) break;
  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
      body: JSON.stringify({
        model: MODEL,
        temperature: attempt === 0 ? 0.3 : 0,
        // Both models tried here emit a separate `reasoning` field before any content, and
        // both draw on the same budget. Too small a budget is spent thinking and the reply
        // arrives with an empty content string and finish_reason "length" — which the UI
        // correctly reported as "returned nothing usable", because it was.
        max_tokens: MAX_TOKENS,
        messages: [
          { role: "system", content: SYSTEM },
          { role: "user", content: JSON.stringify(facts, null, 1) },
          ...(lastFailure.length
            ? [
                {
                  role: "user" as const,
                  content:
                    `Your previous reply was rejected by an automatic check. These figures ` +
                    `appear in it but not in the data you were given: ` +
                    `${lastFailure.join(", ")}. Write it again using only figures present ` +
                    `in the data above. Do not compute anything.`,
                },
              ]
            : []),
        ],
      }),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: `The model provider returned ${res.status}.` },
        { status: 502 }
      );
    }

    const data = await res.json();
    const choice = data?.choices?.[0];
    const text: string = choice?.message?.content?.trim() ?? "";
    if (!text) {
      // Never fall back to `message.reasoning`. That field is the model's scratch work, it
      // is not written for a reader, and it is exactly the kind of text that would put an
      // unchecked number in front of a visitor.
      const why =
        choice?.finish_reason === "length"
          ? "The model ran out of budget before answering."
          : "The model returned nothing usable.";
      return NextResponse.json({ error: why }, { status: 502 });
    }

    // The gate for prose. Same shape as the risk gate on the trading side: the model
    // proposes, something deterministic decides whether it is allowed through.
    const check = verifyBriefing(text, facts, {
      forbidToday: !facts.latest_session_is_today,
    });
    if (!check.ok) {
      lastFailure = check.unverified;
      continue;
    }

    cache = { key: cacheKey, text, at: Date.now(), checked: check.checked };
    return NextResponse.json({
      text,
      model: MODEL,
      cached: false,
      at: cache.at,
      figuresChecked: check.checked,
    });
  } catch {
    return NextResponse.json({ error: "The model did not answer in time." }, { status: 504 });
  }
  }

  // Fails closed. An unverifiable briefing is not shown at all — a page that promises every
  // number is traceable cannot make an exception for the paragraph a model wrote.
  return NextResponse.json(
    {
      error:
        `The model's reply was rejected: it stated ${lastFailure.length === 1 ? "a figure" : "figures"} ` +
        `not present in the record (${lastFailure.join(", ")}). Nothing is shown rather than ` +
        `something unverified.`,
      rejected: lastFailure,
    },
    { status: 422 }
  );
}
