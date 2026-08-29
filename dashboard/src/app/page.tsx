import { getAuditRecords } from "@/lib/audit";
import { EquityChart } from "@/components/equity-chart";
import { CycleTable } from "@/components/cycle-table";
import { ModelComparison } from "@/components/model-comparison";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

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

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="space-y-1">
        <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
          Alpaca AI Trading Agents · Options Alpha
        </div>
        <h1 className="font-mono text-2xl font-semibold tracking-tight">
          Agent Dashboard <span className="text-muted-foreground">(read-only)</span>
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Groq is the only model that reaches order execution — every other model
          below runs the same decision each cycle as a logged shadow comparison and
          never touches the account. All risk sizing is deterministic Python, never
          LLM math.
        </p>
      </header>

      <EquityChart records={records} />

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              Cycles logged
            </CardTitle>
          </CardHeader>
          <CardContent className="font-mono text-2xl tabular-nums">{liveCycles}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              Risk gate approved
            </CardTitle>
          </CardHeader>
          <CardContent
            className="font-mono text-2xl tabular-nums"
            style={{ color: "light-dark(#0ca30c, #0ca30c)" }}
          >
            {approvedCount}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              Risk gate rejected
            </CardTitle>
          </CardHeader>
          <CardContent
            className="font-mono text-2xl tabular-nums"
            style={{ color: "light-dark(#d03b3b, #e66767)" }}
          >
            {rejectedCount}
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <h2 className="font-mono text-sm font-semibold uppercase tracking-[0.15em] text-muted-foreground">
          Live vs. shadow — most recent cycles
        </h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {recentForComparison.map((r, i) => (
            <div key={`${r.timestamp}-${i}`} className="space-y-1.5">
              <div className="flex items-center justify-between px-1">
                <span className="font-mono text-xs font-medium">{r.underlying}</span>
                <span className="font-mono text-[10px] text-muted-foreground">
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
            <p className="col-span-full py-8 text-center text-sm text-muted-foreground">
              No cycles logged yet.
            </p>
          )}
        </div>
      </section>

      <Separator />

      <section className="space-y-3">
        <h2 className="font-mono text-sm font-semibold uppercase tracking-[0.15em] text-muted-foreground">
          All trade cycles
        </h2>
        <CycleTable records={records} />
      </section>

      <footer className="pt-4 font-mono text-[10px] text-muted-foreground">
        Data source: audit_log.jsonl, pushed by the scheduler after each cycle. This
        page fetches it fresh on every request — nothing here is cached at build
        time.
      </footer>
    </div>
  );
}
