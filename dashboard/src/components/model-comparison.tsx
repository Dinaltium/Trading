import type { CycleRecord, ModelDecision } from "@/lib/audit";
import { StrategyBadge } from "@/components/strategy-badge";
import { VerdictBadge } from "@/components/verdict-badge";

const SHADOW_LABELS: Record<string, string> = {
  featherless: "Featherless",
  mistral: "Mistral",
  claude_code_cli: "Claude Code CLI",
};

function ModelBlock({
  label,
  isLive,
  decision,
  ok,
  error,
}: {
  label: string;
  isLive: boolean;
  decision: ModelDecision | null | undefined;
  ok: boolean;
  error?: string | null;
}) {
  return (
    <div className="py-2.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs uppercase tracking-[0.15em] text-muted-foreground">
            {label}
          </span>
          {isLive && (
            <span className="rounded-full bg-foreground px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider text-background">
              live — can execute
            </span>
          )}
        </div>
        {ok && decision ? (
          <div className="flex items-center gap-2">
            <StrategyBadge strategy={decision.selected_strategy} />
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              {(decision.confidence_score * 100).toFixed(0)}% confidence
            </span>
          </div>
        ) : (
          <span className="font-mono text-xs text-destructive">{error ? "call failed" : "no data"}</span>
        )}
      </div>
      {/* Whitebox: full reasoning text, every model, always visible — never truncated. */}
      {ok && decision?.reasoning && (
        <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {decision.reasoning}
        </p>
      )}
      {!ok && error && (
        <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-destructive break-words">{error}</p>
      )}
    </div>
  );
}

export function ModelComparison({ record }: { record: CycleRecord }) {
  const shadows = record.shadow_decisions ?? {};
  const s = record.signals;

  return (
    <div className="rounded-xl border p-4">
      {/* Whitebox: the exact signal values every model was given, in full. */}
      {s && (
        <div className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 border-b pb-3 font-mono text-[11px] text-muted-foreground sm:grid-cols-3">
          <span>price ${s.current_price?.toFixed(2)}</span>
          <span>P(Up) {s.classifier_p_up?.toFixed(3)}</span>
          <span>IV rank {s.iv_rank != null ? s.iv_rank.toFixed(1) : "—"}</span>
          <span>IV pct {s.iv_percentile != null ? s.iv_percentile.toFixed(1) : "—"}</span>
          <span>VRP {s.vrp?.toFixed(4)}</span>
          <span>regime {s.market_regime}</span>
        </div>
      )}

      <ModelBlock label="Groq" isLive decision={record.live_decision} ok={!!record.live_decision} />
      <div className="border-t" />
      {(["claude_code_cli", "featherless", "mistral"] as const).map((key) => {
        const sh = shadows[key];
        return (
          <div key={key} className="border-t first:border-t-0">
            <ModelBlock
              label={SHADOW_LABELS[key]}
              isLive={false}
              decision={sh?.decision}
              ok={!!sh?.ok}
              error={sh?.error}
            />
          </div>
        );
      })}

      {record.risk_gate_verdict && (
        <div className="mt-1 flex items-center justify-between border-t pt-2">
          <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Risk gate
          </span>
          <div className="flex items-center gap-2">
            <VerdictBadge approved={record.risk_gate_verdict.approved} />
          </div>
        </div>
      )}
      {record.risk_gate_verdict?.reason && (
        <p className="font-mono text-[11px] leading-relaxed text-muted-foreground">
          {record.risk_gate_verdict.reason}
        </p>
      )}
    </div>
  );
}
