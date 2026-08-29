// Reads audit-cycle records the Python scheduler pushes to GitHub after each tick
// (see src/audit_log.py, src/scheduler.py in the repo root). The deployed dashboard
// has no access to the local machine's filesystem, so this fetches the raw file from
// GitHub on every request rather than reading a local path — see BRAINSTORM.md for why.

const RAW_URL =
  "https://raw.githubusercontent.com/Dinaltium/Trading/main/logs/audit_log.jsonl";

export type ModelDecision = {
  selected_strategy: "bull_call_spread" | "bear_put_spread" | "iron_condor" | "cash";
  confidence_score: number;
  reasoning: string;
  approved_for_execution: boolean;
};

export type LiveDecision = ModelDecision & { provider: "groq" };

export type ShadowResult = {
  ok: boolean;
  decision: ModelDecision | null;
  error: string | null;
};

export type RiskGateVerdict = {
  approved: boolean;
  reason: string;
  contracts?: number;
};

export type CycleSignals = {
  underlying: string;
  current_price: number;
  classifier_p_up: number;
  iv_rank: number | null;
  iv_percentile: number | null;
  iv_history_days: number;
  vrp: number;
  market_regime: string;
  days_to_earnings: number | null;
};

export type FillResult = {
  order_id?: string;
  status?: string;
  dry_run?: boolean;
  would_submit?: string;
  contracts?: number;
} | null;

export type CycleRecord = {
  timestamp: string;
  underlying: string;
  dry_run: boolean;
  account_equity: number | null;
  signals: CycleSignals;
  live_decision: LiveDecision | null;
  shadow_decisions: {
    featherless?: ShadowResult;
    mistral?: ShadowResult;
    claude_code_cli?: ShadowResult;
  };
  risk_gate_verdict: RiskGateVerdict | null;
  fill_result: FillResult;
};

export async function getAuditRecords(): Promise<CycleRecord[]> {
  const res = await fetch(RAW_URL, { cache: "no-store" });
  if (!res.ok) {
    if (res.status === 404) return []; // log not pushed yet
    throw new Error(`failed to fetch audit log: ${res.status}`);
  }
  const text = await res.text();
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  const records: CycleRecord[] = [];
  for (const line of lines) {
    try {
      records.push(JSON.parse(line));
    } catch {
      // one malformed line (e.g. a partial write mid-push) shouldn't sink the whole dashboard
      continue;
    }
  }
  return records;
}
