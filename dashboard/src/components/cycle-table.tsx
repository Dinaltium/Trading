import type { CycleRecord } from "@/lib/audit";
import { StrategyBadge } from "@/components/strategy-badge";
import { VerdictBadge } from "@/components/verdict-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function CycleTable({ records }: { records: CycleRecord[] }) {
  const sorted = [...records].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  return (
    <div className="w-full min-w-0 space-y-2">
      {/* The table is ~610px wide and scrolls inside its own box on a phone. Without a hint
          that scroll is invisible: the row just looks truncated at "Groq decision". */}
      <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground sm:hidden">
        scroll sideways for the full row →
      </p>
      <div className="w-full min-w-0 overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-mono text-[10px] uppercase tracking-[0.15em]">Time</TableHead>
              <TableHead className="font-mono text-[10px] uppercase tracking-[0.15em]">Symbol</TableHead>
              <TableHead className="font-mono text-[10px] uppercase tracking-[0.15em]">P(Up)</TableHead>
              <TableHead className="font-mono text-[10px] uppercase tracking-[0.15em]">IV Rank</TableHead>
              <TableHead className="font-mono text-[10px] uppercase tracking-[0.15em]">VRP</TableHead>
              <TableHead className="font-mono text-[10px] uppercase tracking-[0.15em]">Groq decision</TableHead>
              <TableHead className="font-mono text-[10px] uppercase tracking-[0.15em]">Risk gate</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((r, i) => (
              <TableRow key={`${r.timestamp}-${r.underlying}-${i}`}>
                <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                  {new Date(r.timestamp).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </TableCell>
                <TableCell className="font-mono text-xs font-medium">{r.underlying}</TableCell>
                <TableCell className="font-mono text-xs tabular-nums">
                  {r.signals?.classifier_p_up != null ? r.signals.classifier_p_up.toFixed(3) : "—"}
                </TableCell>
                <TableCell className="font-mono text-xs tabular-nums">
                  {r.signals?.iv_rank != null ? r.signals.iv_rank.toFixed(1) : "—"}
                </TableCell>
                <TableCell className="font-mono text-xs tabular-nums">
                  {r.signals?.vrp != null ? r.signals.vrp.toFixed(4) : "—"}
                </TableCell>
                <TableCell>
                  <StrategyBadge strategy={r.live_decision?.selected_strategy} />
                </TableCell>
                <TableCell>
                  <VerdictBadge approved={r.risk_gate_verdict?.approved} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          </Table>
      </div>
    </div>
  );
}
