import { getAuditRecords } from "@/lib/audit";
import { EquityChart } from "@/components/equity-chart";
import { CycleTable } from "@/components/cycle-table";
import { ModelComparison } from "@/components/model-comparison";
import { StatTile } from "@/components/stat-tile";
import { Separator } from "@/components/ui/separator";
import { LiveRefresh } from "@/components/live-refresh";
import { SessionSummary } from "@/components/session-summary";
import { ModelBriefing } from "@/components/model-briefing";

// Read-only dashboard, no forms/buttons that touch the account. Data source is
// GitHub (see lib/audit.ts), re-fetched with no caching so this always reflects
// the latest pushed scheduler cycle — never a build-time snapshot.
export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const records = await getAuditRecords();
  const sortedDesc = [...records].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );
  const recentForComparison = sortedDesc.slice(0, 6);

  const approvedCount = records.filter((r) => r.risk_gate_verdict?.approved).length;
  const rejectedCount = records.filter(
    (r) => r.risk_gate_verdict && !r.risk_gate_verdict.approved
  ).length;
  const liveCycles = records.length;

  // min-w-0 on the wrapper below is load-bearing. <body> is a flex column, so that div is a
  // flex item, and a flex item's default min-width:auto resolves to its min-content width.
  // The cycle table's min-content is ~644px, so on a 375px phone the whole page inflated to
  // 644 and every section overflowed sideways — the table's own overflow-x-auto never got
  // the chance to scroll, because nothing was ever narrower than the table.
  return (
    <div className="mx-auto w-full min-w-0 max-w-7xl space-y-8 p-4 sm:p-8">
      <header className="space-y-2 border-b-2 border-b-[var(--brand-olive)]/35 pb-6">
        {/* The kicker is 40 characters of letter-spaced mono. At 0.25em it needs ~430px and
            wrapped mid-phrase on every phone; the tracking relaxes until there is room. */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--brand-olive-deep)] sm:text-[11px] sm:tracking-[0.25em]">
            Alpaca AI Trading Agents · Options Alpha
          </div>
          <LiveRefresh />
        </div>
        <h1 className="text-[1.4rem] font-semibold tracking-tight sm:text-[1.7rem]">
          Brightline <span className="font-normal text-muted-foreground">— read-only</span>
        </h1>
        <p className="max-w-2xl text-[0.95rem] leading-relaxed text-muted-foreground">
          Groq is the only model that reaches order execution — every other model
          below runs the same decision each cycle as a logged shadow comparison and
          never touches the account. All risk sizing is deterministic Python, never
          LLM math.
        </p>
      </header>

      <SessionSummary records={records} />

      <EquityChart records={records} />

      <ModelBriefing />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
        {/* Three tiles into two columns leaves a hole; the count spans the row instead. */}
        <div className="col-span-2 sm:col-span-1">
          <StatTile label="Cycles logged" value={liveCycles} />
        </div>
        <StatTile label="Risk gate approved" value={approvedCount} tone="good" />
        <StatTile label="Risk gate rejected" value={rejectedCount} tone="critical" />
      </div>

      <section className="space-y-4">
        <div>
          <h2 className="flex items-center gap-2.5 text-base font-semibold tracking-tight">
            <span className="inline-block h-3.5 w-1 rounded-full bg-[var(--brand-olive)]" />
            Live vs. shadow
          </h2>
          <p className="text-sm text-muted-foreground">Most recent cycles, full reasoning, nothing truncated.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {recentForComparison.map((r, i) => (
            <div key={`${r.timestamp}-${i}`} className="space-y-2">
              <div className="flex items-center justify-between px-0.5">
                <span className="text-sm font-semibold">{r.underlying}</span>
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {new Date(r.timestamp).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <ModelComparison record={r} />
            </div>
          ))}
          {recentForComparison.length === 0 && (
            <p className="col-span-full py-10 text-center text-sm text-muted-foreground">
              No cycles logged yet — check back after the next scheduled run.
            </p>
          )}
        </div>
      </section>

      <Separator />

      <section className="space-y-4">
        <div>
          <h2 className="flex items-center gap-2.5 text-base font-semibold tracking-tight">
            <span className="inline-block h-3.5 w-1 rounded-full bg-[var(--brand-olive)]" />
            All trade cycles
          </h2>
          <p className="text-sm text-muted-foreground">Full history, most recent first.</p>
        </div>
        <CycleTable records={records} />
      </section>

      <footer className="border-t pt-5 text-xs text-muted-foreground">
        Data source:{" "}
        <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">audit_log.jsonl</code>,
        pushed after every cycle by a GitHub Actions workflow running on a 15-minute
        schedule — not anyone&apos;s laptop. This page fetches it fresh on every
        request, never cached at build time.
      </footer>
    </div>
  );
}
