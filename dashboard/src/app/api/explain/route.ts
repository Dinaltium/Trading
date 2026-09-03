import { NextResponse } from "next/server";
import { getAuditRecords } from "@/lib/audit";
import { buildSummary, daysRunning, INCEPTION_EQUITY } from "@/lib/summary";

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

const GROQ_URL = "https://api.groq.com/openai/v1/chat/completions";
const MODEL = "openai/gpt-oss-120b"; // the same model that trades — see PROVIDERS in src/model_adapter.py

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
7. strategy_mix counts what the live model PROPOSED this session. It is not a list of open
   positions and must never be described as what the agent currently holds.

Three short paragraphs, plain prose, no headings, no bullet points, no markdown. Around 130
words. Address the reader directly. Be plain, not promotional.`;

// One briefing per state of the log. Repeated clicks on an unchanged page cost nothing, and
// a public endpoint that bills per press is a bad idea on a URL anyone can open.
let cache: { key: string; text: string; at: number } | null = null;

export async function GET() {
  const key = process.env.GROQ_API_KEY;
  if (!key) {
    return NextResponse.json(
      { error: "No GROQ_API_KEY configured on this deployment." },
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
      session_date: s.sessionLabel,
      cycles_this_session: s.cyclesToday,
      underlyings: s.underlyings,
      equity_now: s.equityNow,
      equity_at_session_open: s.equityOpen,
      equity_at_inception: INCEPTION_EQUITY,
      change_since_inception: s.equityNow - INCEPTION_EQUITY,
      pct_since_inception: +(((s.equityNow - INCEPTION_EQUITY) / INCEPTION_EQUITY) * 100).toFixed(2),
      all_time_high: s.peak,
      all_time_low: s.trough,
      proposals_this_session: s.proposed,
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
    return NextResponse.json({ text: cache.text, model: MODEL, cached: true, at: cache.at });
  }

  try {
    const res = await fetch(GROQ_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
      body: JSON.stringify({
        model: MODEL,
        temperature: 0.3,
        // This model emits a separate `reasoning` field before any content, and both are
        // drawn from the same budget. At 500 the budget was spent thinking and the reply
        // came back with an empty content string and finish_reason "length" — which the UI
        // correctly reported as "returned nothing usable", because it was.
        max_tokens: 1500,
        reasoning_effort: "low",
        messages: [
          { role: "system", content: SYSTEM },
          { role: "user", content: JSON.stringify(facts, null, 1) },
        ],
      }),
      signal: AbortSignal.timeout(25_000),
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

    cache = { key: cacheKey, text, at: Date.now() };
    return NextResponse.json({ text, model: MODEL, cached: false, at: cache.at });
  } catch {
    return NextResponse.json({ error: "The model did not answer in time." }, { status: 504 });
  }
}
