// Status colors are reserved (good/critical) and never reused for series identity,
// per the dataviz skill — approved/rejected here is a genuine binary system state,
// not a category, so status color is the right tool. Icon + label, never color alone.
export function VerdictBadge({ approved }: { approved: boolean | null | undefined }) {
  if (approved === null || approved === undefined) {
    return (
      <span className="rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
        no trade
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[11px] font-medium"
      style={{
        color: approved ? "light-dark(#0ca30c, #0ca30c)" : "light-dark(#a04141, #e66767)",
        background: approved
          ? "light-dark(color-mix(in srgb, #0ca30c 8%, transparent), color-mix(in srgb, #0ca30c 14%, transparent))"
          : "light-dark(color-mix(in srgb, #d03b3b 8%, transparent), color-mix(in srgb, #e66767 14%, transparent))",
      }}
    >
      {approved ? "✓ approved" : "✕ rejected"}
    </span>
  );
}
