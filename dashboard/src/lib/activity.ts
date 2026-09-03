import type { CycleRecord, Provider } from "@/lib/audit";

// Flattens audit records into a running feed of what the agent did, one line per event.
//
// The chart says what the account is worth and the table says what was decided; neither
// shows the sequence. A reader who lands here cold cannot tell, from a table, that the agent
// looked at SPY every fifteen minutes all day and declined every time — that reads as
// inactivity rather than as the system working. As a feed it reads as what it is.
//
// Every line is derived from a record that is already on the page. Nothing is generated,
// nothing is streamed from a live process, and no event appears here that is not in
// logs/audit_log.jsonl.

export type ActivityKind = "cycle" | "signal" | "decision" | "approved" | "refused" | "fill" | "error";

export type ActivityEvent = {
  at: string;
  kind: ActivityKind;
  underlying: string;
  text: string;
};

function pct(n: number | null | undefined, digits = 2): string {
  return n == null ? "—" : n.toFixed(digits);
}

/** Newest first. A feed that grows downward needs the reader to scroll to find what just
 *  happened, and auto-scrolling a page the reader is already reading is worse. */
export function buildActivity(records: CycleRecord[], limit = 60): ActivityEvent[] {
  const sorted = [...records].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  const events: ActivityEvent[] = [];

  for (const r of sorted) {
    if (events.length >= limit) break;
    const at = r.timestamp;
    const u = r.underlying;
    const push = (kind: ActivityKind, text: string) => events.push({ at, kind, underlying: u, text });

    const fill = r.fill_result;
    if (fill?.status) {
      push("fill", `order ${fill.status}${fill.contracts ? ` · ${fill.contracts} contracts` : ""}`);
    }

    const gate = r.risk_gate_verdict;
    if (gate) {
      if (gate.approved) {
        push("approved", `risk gate approved${gate.contracts ? ` · ${gate.contracts} contracts` : ""}`);
      } else {
        // The reason is the most valuable string in the record. It is never truncated.
        push("refused", `risk gate refused · ${gate.reason}`);
      }
    }

    if (r.live_decision_error) {
      push("error", `live model produced no usable decision · ${r.live_decision_error}`);
    } else if (r.live_decision) {
      const shadows = Object.entries(r.shadow_decisions ?? {})
        .map(([name, s]) => {
          const pick = (s as { decision?: { selected_strategy?: string } })?.decision?.selected_strategy;
          return pick ? `${name}:${pick.replace(/_/g, " ")}` : null;
        })
        .filter(Boolean);
      const agreed = shadows.length
        ? ` · shadows ${shadows.join(", ")}`
        : "";
      push(
        "decision",
        `${r.live_decision.provider} chose ${r.live_decision.selected_strategy.replace(/_/g, " ")}` +
          `${agreed}`
      );
    }

    const s = r.signals;
    if (s) {
      push(
        "signal",
        `P(up) ${pct(s.classifier_p_up, 3)} · IV rank ${
          s.iv_rank == null ? "untrusted" : pct(s.iv_rank, 1)
        } · ${s.market_regime?.toLowerCase().replace(/_/g, " ") ?? "regime unknown"}`
      );
    }

    push("cycle", `cycle · ${u}${s?.current_price ? ` at $${s.current_price.toFixed(2)}` : ""}`);
  }

  return events.slice(0, limit);
}

export const KIND_LABEL: Record<ActivityKind, string> = {
  cycle: "CYCLE",
  signal: "SIGNAL",
  decision: "MODEL",
  approved: "GATE",
  refused: "GATE",
  fill: "ORDER",
  error: "ERROR",
};
