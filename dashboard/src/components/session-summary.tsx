import type { CycleRecord } from "@/lib/audit";
import { buildSummary, daysRunning, INCEPTION_EQUITY } from "@/lib/summary";
import { strategyLabel } from "@/lib/strategy-colors";

function money(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function signed(n: number): string {
  return `${n >= 0 ? "+" : "−"}${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

/** The number reads as prose, so it gets prose emphasis: same weight as the sentence, but
 *  monospaced, because a machine produced it. The Two Voices Rule holds inside a paragraph. */
function Fig({ children }: { children: React.ReactNode }) {
  return <span className="font-mono text-[0.95em] tabular-nums text-foreground">{children}</span>;
}

export function SessionSummary({ records }: { records: CycleRecord[] }) {
  const s = buildSummary(records);
  if (!s || s.equityNow == null) return null;

  const days = daysRunning(s.firstSeen);
  const sinceOpen = s.equityOpen != null ? s.equityNow - s.equityOpen : null;
  const sinceStart = s.equityNow - INCEPTION_EQUITY;
  const startPct = (sinceStart / INCEPTION_EQUITY) * 100;

  return (
    <section className="rounded-xl border border-[var(--brand-olive)]/35 bg-[var(--brand-olive)]/[0.055] p-5 sm:p-6">
      <h2 className="flex items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.15em] text-[var(--brand-olive-deep)]">
        <span className="inline-block h-3 w-1 rounded-full bg-[var(--brand-olive)]" />
        Where it stands
      </h2>

      <p className="mt-3 max-w-3xl text-[0.95rem] leading-relaxed text-foreground/85">
        The agent has run <Fig>{s.totalCycles}</Fig> decision cycles over{" "}
        <Fig>{days}</Fig> {days === 1 ? "day" : "days"}, and{" "}
        <Fig>{s.cyclesToday}</Fig> of them in the session of{" "}
        <Fig>{s.sessionLabel}</Fig> across {s.underlyings.join(", ")}. Equity stands at{" "}
        <Fig>{money(s.equityNow)}</Fig>
        {sinceOpen != null && (
          <>
            {" "}
            against <Fig>{money(s.equityOpen!)}</Fig> at the session&apos;s first cycle, a move of{" "}
            <Fig>{signed(sinceOpen)}</Fig>
          </>
        )}
        . Since the account opened at {money(INCEPTION_EQUITY)} that is{" "}
        <Fig>
          {signed(sinceStart)} ({startPct >= 0 ? "+" : "−"}
          {Math.abs(startPct).toFixed(2)}%)
        </Fig>
        {s.peak != null && s.trough != null && (
          <>
            , inside a range of <Fig>{money(s.trough)}</Fig> to <Fig>{money(s.peak)}</Fig>
          </>
        )}
        .
      </p>

      <p className="mt-3 max-w-3xl text-[0.95rem] leading-relaxed text-foreground/85">
        This session the live model asked to trade on <Fig>{s.proposed}</Fig>{" "}
        {s.proposed === 1 ? "cycle" : "cycles"}. The risk gate returned a verdict{" "}
        <Fig>{s.approved + s.refused}</Fig> times (it also rules on cycles the model sat
        out), approving <Fig>{s.approved}</Fig> and refusing <Fig>{s.refused}</Fig>
        {s.topRefusal && (
          <>
            {" "}
            — most often because it was {s.topRefusal.reason} (
            <Fig>{s.topRefusal.count}</Fig> {s.topRefusal.count === 1 ? "time" : "times"})
          </>
        )}
        . <Fig>{s.submitted}</Fig>{" "}
        {s.submitted === 1 ? "order reached" : "orders reached"} the broker.
        {s.strategyMix.length > 0 && (
          <>
            {" "}
            Its picks were{" "}
            {s.strategyMix.map((m, i) => (
              <span key={m.strategy}>
                {i > 0 && (i === s.strategyMix.length - 1 ? " and " : ", ")}
                <Fig>{m.count}</Fig>× {strategyLabel(m.strategy).toLowerCase()}
              </span>
            ))}
            .
          </>
        )}
      </p>

      <p className="mt-3 max-w-3xl text-[0.95rem] leading-relaxed text-foreground/85">
        Three models saw the same signal vector every cycle and one of them could execute.
        They landed on different answers in <Fig>{s.disagreedToday}</Fig> of{" "}
        <Fig>{s.scoredToday}</Fig> scored cycles this session
        {s.scoredToday > 0 && (
          <>
            {" "}
            (
            <Fig>{Math.round((s.disagreedToday / s.scoredToday) * 100)}%</Fig>)
          </>
        )}
        . Their reasoning is quoted in full below, including the two that were never allowed
        to act on it.
      </p>

      <p className="mt-4 border-t border-[var(--brand-olive)]/25 pt-3 text-xs leading-relaxed text-muted-foreground">
        Every figure above is computed from the same audit records shown below — no language
        model writes this paragraph. A model narrating live P&amp;L can state a number that
        was never true, and the claim this project makes is that the deterministic layer is
        the part you can check.
      </p>
    </section>
  );
}
