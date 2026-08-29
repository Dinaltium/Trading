import type { CycleRecord, ModelDecision } from "@/lib/audit";
import { StrategyBadge } from "@/components/strategy-badge";
import { VerdictBadge } from "@/components/verdict-badge";

const SHADOW_LABELS: Record<string, string> = {
  featherless: "Featherless",
  mistral: "Mistral",
  claude_code_cli: "Claude Code CLI",
};

function SignalStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{label}</span>
      <span className="font-mono text-[13px] tabular-nums break-words">{value}</span>
    </div>
  );
}

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
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{label}</span>
          {isLive && (
            <span className="rounded-full bg-foreground px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-background">
              live · can execute
            </span>
          )}
        </div>
        {ok && decision ? (
          <div className="flex items-center gap-2">
            <StrategyBadge strategy={decision.selected_strategy} />
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              {(decision.confidence_score * 100).toFixed(0)}%
            </span>
          </div>
        ) : (
          <span
            className="rounded-full px-2 py-0.5 font-mono text-[11px]"
            style={{
              color: "light-dark(#a04141, #e66767)",
              background: "light-dark(color-mix(in srgb, #d03b3b 8%, transparent), color-mix(in srgb, #e66767 14%, transparent))",
            }}
          >
            {error ? "call failed" : "no data"}
          </span>
        )}
      </div>
      {/* Whitebox: full reasoning, every model, always visible — never truncated, never a tooltip. */}
      {ok && decision?.reasoning && (
        <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{decision.reasoning}</p>
      )}
      {!ok && error && (
        <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground break-words">{error}</p>
      )}
    </div>
  );
}

export function ModelComparison({ record }: { record: CycleRecord }) {
  const shadows = record.shadow_decisions ?? {};
  const s = record.signals;

  return (
    <div className="rounded-xl border bg-card p-4 transition-colors hover:border-foreground/20">
      {/* Whitebox: the exact signal values every model was given, in full. */}
      {s && (
        <div className="mb-3.5 grid grid-cols-3 gap-x-3 gap-y-2.5 border-b pb-3.5">
          <SignalStat label="Price" value={`$${s.current_price?.toFixed(2)}`} />
          <SignalStat label="P(Up)" value={s.classifier_p_up?.toFixed(3) ?? "—"} />
          <SignalStat label="IV rank" value={s.iv_rank != null ? s.iv_rank.toFixed(1) : "—"} />
          <SignalStat label="IV pct" value={s.iv_percentile != null ? s.iv_percentile.toFixed(1) : "—"} />
          <SignalStat label="VRP" value={s.vrp?.toFixed(4) ?? "—"} />
          <SignalStat label="Regime" value={s.market_regime ?? "—"} />
        </div>
      )}

      <div className="divide-y">
        <ModelBlock label="Groq" isLive decision={record.live_decision} ok={!!record.live_decision} />
        {(["claude_code_cli", "featherless", "mistral"] as const).map((key) => {
          const sh = shadows[key];
          return (
            <ModelBlock
              key={key}
              label={SHADOW_LABELS[key]}
              isLive={false}
              decision={sh?.decision}
              ok={!!sh?.ok}
              error={sh?.error}
            />
          );
        })}
      </div>

      {record.risk_gate_verdict && (
        <div className="mt-1 border-t pt-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
              Risk gate
            </span>
            <VerdictBadge approved={record.risk_gate_verdict.approved} />
          </div>
          {record.risk_gate_verdict.reason && (
            <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
              {record.risk_gate_verdict.reason}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
