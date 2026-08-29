import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TONE_STYLES = {
  neutral: { fg: "var(--foreground)", bg: "transparent" },
  good: { fg: "light-dark(#0ca30c, #0ca30c)", bg: "light-dark(color-mix(in srgb, #0ca30c 7%, transparent), color-mix(in srgb, #0ca30c 12%, transparent))" },
  critical: { fg: "light-dark(#d03b3b, #e66767)", bg: "light-dark(color-mix(in srgb, #d03b3b 6%, transparent), color-mix(in srgb, #e66767 12%, transparent))" },
} as const;

export function StatTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number;
  tone?: keyof typeof TONE_STYLES;
}) {
  const style = TONE_STYLES[tone];
  return (
    <Card style={{ background: style.bg }}>
      <CardHeader className="pb-1.5">
        <CardTitle className="font-mono text-[11px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="font-mono text-[1.75rem] font-semibold tabular-nums" style={{ color: style.fg }}>
        {value}
      </CardContent>
    </Card>
  );
}
