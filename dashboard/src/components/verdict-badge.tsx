// Status colors are reserved (good/critical) and never reused for series identity,
// per the dataviz skill — approved/rejected here is a genuine binary system state,
// not a category, so status color is the right tool. Icon + label, never color alone.
export function VerdictBadge({ approved }: { approved: boolean | null | undefined }) {
  if (approved === null || approved === undefined) {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-xs text-muted-foreground">
        — no trade
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 font-mono text-xs font-medium"
      style={{ color: approved ? "light-dark(#0ca30c, #0ca30c)" : "light-dark(#d03b3b, #e66767)" }}
    >
      {approved ? "✓ approved" : "✕ rejected"}
    </span>
  );
}
