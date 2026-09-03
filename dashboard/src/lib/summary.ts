import type { CycleRecord, Provider } from "@/lib/audit";

// A plain-language account of what the agent did, derived entirely from the audit log.
//
// Deliberately not written by a model. Every figure here is computed from the same records
// rendered below it, so the prose cannot drift from the table it sits above. A language
// model narrating live P&L can produce a number that was never true, and one fabricated
// figure on this page would cost more than the paragraph is worth — the whole claim is that
// the deterministic layer is what you can rely on. The models' own words are already on the
// page, quoted in full; this narrates them rather than replacing them.

const MS_PER_DAY = 86_400_000;
const START_EQUITY = 100_000;

export type SessionSummary = {
  sessionLabel: string;
  cyclesToday: number;
  underlyings: string[];
  proposed: number;
  refused: number;
  approved: number;
  submitted: number;
  topRefusal: { reason: string; count: number } | null;
  equityOpen: number | null;
  equityNow: number | null;
  peak: number | null;
  trough: number | null;
  disagreedToday: number;
  scoredToday: number;
  strategyMix: { strategy: string; count: number }[];
  totalCycles: number;
  firstSeen: string | null;
};

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

/** Collapses a gate reason to the rule that produced it, so "already holding SPY; one
 *  position per underlying" and the same phrase for QQQ count as one recurring rule rather
 *  than as two unrelated events. */
function refusalRule(reason: string): string {
  const r = reason.toLowerCase();
  if (r.includes("one position per underlying")) return "already holding that underlying";
  if (r.includes("max_underlyings_concurrent")) return "at the concurrent-underlying cap";
  if (r.includes("premium-selling halt")) return "premium-selling halted on high IV rank";
  if (r.includes("drawdown")) return "daily drawdown limit";
  if (r.includes("open risk") || r.includes("max_total_open_risk")) return "open-risk budget spent";
  if (r.includes("consecutive")) return "restricted after consecutive losses";
  if (r.includes("expiry") || r.includes("dte")) return "no expiry it is allowed to trade";
  return reason.split(";")[0].trim();
}

export function buildSummary(records: CycleRecord[]): SessionSummary | null {
  if (records.length === 0) return null;

  const sorted = [...records].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );
  const latestDay = dayKey(sorted[sorted.length - 1].timestamp);
  const today = sorted.filter((r) => dayKey(r.timestamp) === latestDay);

  // A "proposal" is the model asking to trade. Cash is a decision, not a proposal, and
  // counting it as one would make the refusal rate look far better than it is.
  const proposals = today.filter(
    (r) => r.live_decision && r.live_decision.selected_strategy !== "cash"
  );
  const verdicts = today.filter((r) => r.risk_gate_verdict);
  const approved = verdicts.filter((r) => r.risk_gate_verdict?.approved).length;
  const refused = verdicts.length - approved;

  const reasons = new Map<string, number>();
  for (const r of verdicts) {
    if (r.risk_gate_verdict?.approved) continue;
    const rule = refusalRule(r.risk_gate_verdict?.reason ?? "");
    if (!rule) continue;
    reasons.set(rule, (reasons.get(rule) ?? 0) + 1);
  }
  const topRefusal =
    [...reasons.entries()].sort((a, b) => b[1] - a[1]).map(([reason, count]) => ({ reason, count }))[0] ??
    null;

  const equities = today.map((r) => r.account_equity).filter((e): e is number => e != null);
  const allEquities = sorted.map((r) => r.account_equity).filter((e): e is number => e != null);

  const mix = new Map<string, number>();
  for (const r of today) {
    const s = r.live_decision?.selected_strategy;
    if (s) mix.set(s, (mix.get(s) ?? 0) + 1);
  }

  // How often the three models landed on different answers from identical inputs. This is
  // the number the shadow benchmark exists to produce; unanimity would mean the extra two
  // models were telling us nothing.
  let disagreed = 0;
  let scored = 0;
  for (const r of today) {
    const picks = new Set<string>();
    if (r.live_decision?.selected_strategy) picks.add(r.live_decision.selected_strategy);
    for (const key of Object.keys(r.shadow_decisions ?? {}) as Provider[]) {
      const s = r.shadow_decisions?.[key]?.decision?.selected_strategy;
      if (s) picks.add(s);
    }
    if (picks.size >= 1) {
      scored += 1;
      if (picks.size > 1) disagreed += 1;
    }
  }

  return {
    sessionLabel: latestDay,
    cyclesToday: today.length,
    underlyings: [...new Set(today.map((r) => r.underlying))].sort(),
    proposed: proposals.length,
    refused,
    approved,
    submitted: today.filter((r) => r.fill_result?.status).length,
    topRefusal,
    equityOpen: equities[0] ?? null,
    equityNow: equities[equities.length - 1] ?? null,
    peak: allEquities.length ? Math.max(...allEquities) : null,
    trough: allEquities.length ? Math.min(...allEquities) : null,
    disagreedToday: disagreed,
    scoredToday: scored,
    strategyMix: [...mix.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([strategy, count]) => ({ strategy, count })),
    totalCycles: records.length,
    firstSeen: sorted[0]?.timestamp ?? null,
  };
}

export function daysRunning(firstSeen: string | null): number {
  if (!firstSeen) return 0;
  return Math.max(1, Math.round((Date.now() - new Date(firstSeen).getTime()) / MS_PER_DAY));
}

export const INCEPTION_EQUITY = START_EQUITY;
