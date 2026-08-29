import { STRATEGY_STYLE, strategyLabel } from "@/lib/strategy-colors";

export function StrategyBadge({ strategy }: { strategy: string | undefined | null }) {
  const style = strategy ? STRATEGY_STYLE[strategy] : undefined;
  const dot = style ? `light-dark(${style.light}, ${style.dark})` : "#898781";

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px] tabular-nums text-foreground"
      style={{ borderColor: "color-mix(in srgb, currentColor 10%, transparent)" }}
    >
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} />
      {strategyLabel(strategy)}
    </span>
  );
}
