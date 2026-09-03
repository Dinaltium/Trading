import type { CycleRecord } from "@/lib/audit";
import { buildActivity, KIND_LABEL, type ActivityKind } from "@/lib/activity";

// A running feed of the agent's own actions, newest first.
//
// Deliberately not a black terminal with green text. Every other entry in this hackathon has
// one, DESIGN.md reserves the page's single dark surface for the equity panel, and a second
// dark block would compete with it for the eye. This is mono on paper: the density reads as
// a log, and colour is spent only where it carries meaning.

const KIND_STYLE: Record<ActivityKind, { dot: string; label: string }> = {
  cycle: { dot: "var(--brand-olive)", label: "text-[var(--brand-olive-deep)]" },
  signal: { dot: "#c9bc9c", label: "text-muted-foreground" },
  decision: { dot: "#2a78d6", label: "text-muted-foreground" },
  approved: { dot: "#0ca30c", label: "text-[#0ca30c]" },
  refused: { dot: "#d03b3b", label: "text-[#d03b3b]" },
  fill: { dot: "#1baf7a", label: "text-[#1baf7a]" },
  error: { dot: "#d03b3b", label: "text-[#d03b3b]" },
};

function clock(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "America/New_York",
  });
}

export function ActivityFeed({ records }: { records: CycleRecord[] }) {
  const events = buildActivity(records, 60);
  if (events.length === 0) return null;

  const refusals = events.filter((e) => e.kind === "refused").length;

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="flex items-center gap-2.5 text-base font-semibold tracking-tight">
          <span className="inline-block h-3.5 w-1 rounded-full bg-[var(--brand-olive)]" />
          Agent activity
        </h2>
        <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
          last {events.length} events · {refusals} refusals · newest first · market time
        </p>
      </div>

      <div className="max-h-[26rem] overflow-y-auto rounded-xl border">
        <ul className="divide-y divide-border">
          {events.map((e, i) => {
            const style = KIND_STYLE[e.kind];
            return (
              <li
                key={`${e.at}-${e.kind}-${i}`}
                className="flex items-start gap-3 px-3 py-1.5 font-mono text-[11px] leading-relaxed sm:px-4"
              >
                <span className="tabular-nums text-muted-foreground">{clock(e.at)}</span>
                <span
                  aria-hidden
                  className="mt-[0.45em] h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: style.dot }}
                />
                <span className={`w-[3.5rem] shrink-0 uppercase tracking-[0.1em] ${style.label}`}>
                  {KIND_LABEL[e.kind]}
                </span>
                <span className="w-9 shrink-0 font-medium text-foreground">{e.underlying}</span>
                {/* min-w-0 so a long refusal reason wraps inside the row instead of pushing
                    the row wider than the page — the same flex trap that inflated the whole
                    document to 644px on a phone. */}
                <span className="min-w-0 flex-1 break-words text-foreground/80">{e.text}</span>
              </li>
            );
          })}
        </ul>
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Every line is read from <code className="font-mono">audit_log.jsonl</code>, the same
        file the table below renders. Nothing here is streamed from a running process or
        written for display — a refusal appears because the gate refused, and it carries the
        reason it gave.
      </p>
    </section>
  );
}
