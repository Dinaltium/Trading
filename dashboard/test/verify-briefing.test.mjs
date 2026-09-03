// Cases for the briefing verifier, including the exact fabrication this model actually
// produced in development: handed 60 proposals and 59 refusals, it wrote that the refusals
// were "the remaining 58" of the proposals.
//
//   npx tsc src/lib/verify-briefing.ts --target es2022 --module es2022 //     --moduleResolution bundler --outDir .
//   mv verify-briefing.js verify-compiled.mjs && node test/verify-briefing.test.mjs
//
const facts = {
  days_running: 4, total_cycles: 203, session_date: "2026-09-02", cycles_this_session: 88,
  underlyings: ["DIA","IWM","QQQ","SPY"], equity_now: 99432.58, equity_at_session_open: 100281.58,
  equity_at_inception: 100000, change_since_inception: -567.42, pct_since_inception: -0.57,
  all_time_high: 104189.58, all_time_low: 99424.58, proposals_this_session: 60,
  gate_verdicts_total: 61, gate_approved: 2, gate_refused: 59,
  most_common_refusal: "already holding that underlying", most_common_refusal_count: 36,
  orders_reaching_broker: 2,
  strategy_mix: [{strategy:"bear_put_spread",count:37},{strategy:"cash",count:28},{strategy:"iron_condor",count:23}],
  models_compared: 3, cycles_where_models_disagreed: 36, cycles_scored: 88,
};
const cases = [
  ["real reply (should PASS)", "You've been looking at the agent after four days, covering 203 total cycles and 88 in the session of September 2, 2026. Equity is now $99,432.58, a change of -$567.42 (-0.57%) from $100,000. The high is $104,189.58 and the low $99,424.58. The gate issued 61 verdicts, approving 2 and refusing 59. The mix was 37 bear-put spreads, 28 cash and 23 iron condors. Three models disagreed on 36 of 88 cycles.", true],
  ["the real hallucination (should FAIL)", "It made 60 proposals, two were approved, and the remaining 58 were refused.", false],
  ["invented percentage (should FAIL)", "Equity is $99,432.58, down 12.4% on the week.", false],
  ["invented count (should FAIL)", "The agent has placed 47 trades since it started.", false],
  ["spaced thousands (should PASS)", "The account started at 100 000 USD and is now 99 432.58 USD.", true],
  ["rounded restatement (should PASS)", "Equity stands at about $99,433 today.", true],
  ["word numbers (should FAIL)", "It compared seven language models this session.", false],
  ["unicode minus (should PASS)", "A move of −567.42, or −0.57 %.", true],
  ["worded remainder, all figures real (should FAIL)", "It proposed 60 trades, the gate approved 2, refusing the remaining 59.", false],
  ["innocent use of remaining (should PASS)", "The remaining 2 spreads expire next week.", true],
];
const { verifyBriefing } = await import("../verify-compiled.mjs");
let pass = 0;
for (const [name, text, expectOk] of cases) {
  const v = verifyBriefing(text, facts);
  const good = v.ok === expectOk;
  if (good) pass++;
  console.log(`${good ? "ok  " : "FAIL"}  ${name}  -> ok=${v.ok} checked=${v.checked} unverified=[${v.unverified}]`);
}
console.log(`\n${pass}/${cases.length} cases behaved as expected`);
