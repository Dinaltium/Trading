"use client";

import { useMemo, useState } from "react";
import type { CycleRecord } from "@/lib/audit";

// Single series (equity), sequential blue hue, per the dataviz skill's validated
// reference palette — see BRAINSTORM.md / the skill's references/palette.md.
// One axis only; a hero delta figure sits beside the chart rather than a second y-axis.
//
// Three things this chart has to survive, all of which it previously did not:
//   - Most records carry no account_equity at all (the field was added later), so "we have
//     records but no plottable ones" is a distinct state from "we have no records".
//   - In dry-run the balance never moves, so min === max. The old domain math divided by a
//     forced range of 1, which pinned a flat line to the very bottom of the box and read as
//     a rendering bug rather than as "nothing has moved yet".
//   - Cycles are not evenly spaced in time (skipped weekends, restarts, missed ticks).
//     Spacing points by array index drew those gaps as if they were regular intervals.

type Point = { t: number; equity: number; label: string };

function buildSeries(records: CycleRecord[]): Point[] {
  return records
    .filter((r) => typeof r.account_equity === "number" && Number.isFinite(r.account_equity))
    .map((r) => ({
      t: new Date(r.timestamp).getTime(),
      equity: r.account_equity as number,
      label: new Date(r.timestamp).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
    }))
    .filter((p) => Number.isFinite(p.t))
    .sort((a, b) => a.t - b.t);
}

const VIZ_TOKENS = `
  .viz-root {
    --surface-1: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --gridline: #e1e0d9;
    --series-equity: #2a78d6;
    --good: #0ca30c;
    --critical: #d03b3b;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .viz-root {
      --surface-1: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --gridline: #2c2c2a;
      --series-equity: #3987e5;
      --good: #0ca30c;
      --critical: #e66767;
    }
  }
  :root[data-theme="dark"] .viz-root {
    --surface-1: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --gridline: #2c2c2a;
    --series-equity: #3987e5;
    --good: #0ca30c;
    --critical: #e66767;
  }
`;

function EmptyState({ message }: { message: string }) {
  return (
    <div className="viz-root rounded-2xl border p-4 sm:p-6" style={{ background: "var(--surface-1)" }}>
      <style>{VIZ_TOKENS}</style>
      <div className="flex h-56 items-center justify-center text-center text-sm text-[var(--text-secondary)]">
        {message}
      </div>
    </div>
  );
}

export function EquityChart({ records }: { records: CycleRecord[] }) {
  const points = useMemo(() => buildSeries(records), [records]);
  const [hover, setHover] = useState<number | null>(null);

  if (points.length === 0) {
    // Distinguish the two causes — "no data yet" and "data that carries no equity figure"
    // look identical on screen but mean very different things to whoever is debugging.
    return (
      <EmptyState
        message={
          records.length === 0
            ? "No cycles logged yet — waiting on the first scheduler tick."
            : `${records.length} cycle${records.length === 1 ? "" : "s"} logged, but none carry an account_equity figure yet.`
        }
      />
    );
  }

  const width = 960;
  const height = 220;
  const padX = 8;
  const padY = 20;

  const minEq = Math.min(...points.map((p) => p.equity));
  const maxEq = Math.max(...points.map((p) => p.equity));
  const isFlat = maxEq - minEq < 1e-9;

  // Pad the domain so the line never sits flush against the top or bottom edge. A dead-flat
  // series gets a symmetric window around its value, which draws it through the middle —
  // visibly "steady", rather than looking like a line that failed to render.
  const pad = isFlat ? Math.max(Math.abs(maxEq) * 0.0005, 1) : (maxEq - minEq) * 0.15;
  const lo = minEq - pad;
  const hi = maxEq + pad;
  const span = hi - lo;

  const t0 = points[0].t;
  const tSpan = points[points.length - 1].t - t0;

  // Position by timestamp, not index, so a gap in the cycle history reads as a gap.
  // A single point (or several sharing one instant) is centred rather than jammed left.
  const x = (i: number) =>
    tSpan > 0
      ? padX + ((points[i].t - t0) / tSpan) * (width - padX * 2)
      : width / 2;
  const y = (v: number) => height - padY - ((v - lo) / span) * (height - padY * 2);

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.equity)}`).join(" ");

  const first = points[0].equity;
  const last = points[points.length - 1].equity;
  const delta = last - first;
  const deltaPct = first !== 0 ? (delta / first) * 100 : 0;
  const isUp = delta >= 0;

  const active = hover !== null ? points[hover] : points[points.length - 1];

  const money = (v: number) =>
    v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // Label the top, middle and bottom of the drawn window. Rendered as HTML rather than SVG
  // <text> because the chart uses preserveAspectRatio="none", which would stretch glyphs.
  const axisTicks = [
    { frac: 0, value: hi },
    { frac: 0.5, value: (hi + lo) / 2 },
    { frac: 1, value: lo },
  ];

  return (
    <div className="viz-root rounded-2xl border p-4 sm:p-6" style={{ background: "var(--surface-1)" }}>
      <style>{VIZ_TOKENS}</style>

      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]">
            Account equity
          </div>
          <div className="font-mono text-2xl tabular-nums text-[var(--text-primary)] sm:text-3xl">
            ${money(active.equity)}
          </div>
          <div className="font-mono text-[10px] text-[var(--muted)]">
            {hover !== null ? active.label : `latest · ${active.label}`}
          </div>
        </div>
        <div className="text-right">
          <div
            className="font-mono text-sm tabular-nums"
            style={{ color: isFlat ? "var(--muted)" : isUp ? "var(--good)" : "var(--critical)" }}
          >
            {isFlat ? "—" : isUp ? "▲" : "▼"} ${money(Math.abs(delta))} (
            {deltaPct >= 0 ? "+" : ""}
            {deltaPct.toFixed(2)}%)
          </div>
          <div className="font-mono text-[10px] text-[var(--muted)]">
            {points.length} point{points.length === 1 ? "" : "s"}
            {isFlat ? " · unchanged" : ""}
          </div>
        </div>
      </div>

      <div className="relative">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-56 w-full"
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const relX = ((e.clientX - rect.left) / rect.width) * width;
            // Nearest point by drawn x position — index arithmetic is wrong now that
            // spacing follows time rather than array order.
            let best = 0;
            let bestDist = Infinity;
            for (let i = 0; i < points.length; i++) {
              const d = Math.abs(x(i) - relX);
              if (d < bestDist) {
                bestDist = d;
                best = i;
              }
            }
            setHover(best);
          }}
        >
          {axisTicks.map((tick) => (
            <line
              key={tick.frac}
              x1={padX}
              x2={width - padX}
              y1={padY + tick.frac * (height - padY * 2)}
              y2={padY + tick.frac * (height - padY * 2)}
              stroke="var(--gridline)"
              strokeDasharray="2 4"
              strokeWidth={1}
            />
          ))}

          {hover !== null && (
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={padY}
              y2={height - padY}
              stroke="var(--muted)"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
          )}

          <path
            d={path}
            fill="none"
            stroke="var(--series-equity)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {points.length <= 60 &&
            points.map((p, i) => (
              <circle
                key={i}
                cx={x(i)}
                cy={y(p.equity)}
                r={hover === i ? 4 : 2.5}
                fill="var(--series-equity)"
                opacity={hover === null || hover === i ? 1 : 0.4}
              />
            ))}
        </svg>

        <div className="pointer-events-none absolute inset-0">
          {axisTicks.map((tick) => (
            <span
              key={tick.frac}
              className="absolute right-1 -translate-y-1/2 bg-[var(--surface-1)] px-1 font-mono text-[10px] tabular-nums text-[var(--muted)]"
              style={{ top: `${((padY + tick.frac * (height - padY * 2)) / height) * 100}%` }}
            >
              ${money(tick.value)}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-2 flex justify-between font-mono text-[10px] text-[var(--muted)]">
        <span>{points[0].label}</span>
        <span>{points[points.length - 1].label}</span>
      </div>

      {isFlat && (
        <p className="mt-3 text-xs text-[var(--text-secondary)]">
          Balance unchanged across every logged cycle — expected while the loop runs in dry-run,
          where decisions and risk checks are real but no order is submitted.
        </p>
      )}
    </div>
  );
}
