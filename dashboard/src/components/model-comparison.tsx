import type { CycleRecord, ModelDecision } from "@/lib/audit";
import { StrategyBadge } from "@/components/strategy-badge";

const SHADOW_LABELS: Record<string, string> = {
  featherless: "Featherless",
  mistral: "Mistral",
  claude_code_cli: "Claude Code CLI",
};

function ModelRow({
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
    <div className="flex items-center justify-between gap-3 py-2">
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs uppercase tracking-[0.15em] text-muted-foreground">
          {label}
        </span>
        {isLive && (
          <span className="rounded-full bg-foreground px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider text-background">
            live
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
        <span className="font-mono text-xs text-muted-foreground" title={error ?? undefined}>
          {error ? "call failed" : "no data"}
        </span>
      )}
    </div>
  );
}

export function ModelComparison({ record }: { record: CycleRecord }) {
  const shadows = record.shadow_decisions ?? {};
  return (
    <div className="rounded-xl border p-4">
      <ModelRow
        label="Groq"
        isLive
        decision={record.live_decision}
        ok={!!record.live_decision}
      />
      <div className="border-t" />
      {(["claude_code_cli", "featherless", "mistral"] as const).map((key) => {
        const s = shadows[key];
        return (
          <div key={key} className="border-t first:border-t-0">
            <ModelRow
              label={SHADOW_LABELS[key]}
              isLive={false}
              decision={s?.decision}
              ok={!!s?.ok}
              error={s?.error}
            />
          </div>
        );
      })}
      {record.live_decision && (
        <p className="mt-2 border-t pt-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {record.live_decision.reasoning}
        </p>
      )}
    </div>
  );
}
