"use client";

import { useMemo, useState } from "react";
import type { CycleRecord } from "@/lib/audit";

// Single series (equity), sequential blue hue, per the dataviz skill's validated
// reference palette — see BRAINSTORM.md / the skill's references/palette.md.
// One axis only; a hero delta figure sits beside the chart rather than a second y-axis.

type Point = { t: number; equity: number; label: string };

function buildSeries(records: CycleRecord[]): Point[] {
  return records
    .filter((r) => typeof r.account_equity === "number")
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
    .sort((a, b) => a.t - b.t);
}

export function EquityChart({ records }: { records: CycleRecord[] }) {
  const points = useMemo(() => buildSeries(records), [records]);
  const [hover, setHover] = useState<number | null>(null);

  if (points.length === 0) {
    return (
      <div className="viz-root flex h-64 items-center justify-center rounded-2xl border text-sm text-[var(--text-secondary)]">
        No equity data yet — waiting on the first scheduler cycle.
      </div>
    );
  }

  const width = 960;
  const height = 220;
  const padX = 8;
  const padY = 20;

  const minEq = Math.min(...points.map((p) => p.equity));
  const maxEq = Math.max(...points.map((p) => p.equity));
  const eqRange = maxEq - minEq || 1;

  const x = (i: number) =>
    padX + (i / Math.max(points.length - 1, 1)) * (width - padX * 2);
  const y = (v: number) =>
    height - padY - ((v - minEq) / eqRange) * (height - padY * 2);

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.equity)}`).join(" ");

  const first = points[0].equity;
  const last = points[points.length - 1].equity;
  const delta = last - first;
  const deltaPct = first !== 0 ? (delta / first) * 100 : 0;
  const isUp = delta >= 0;

  const active = hover !== null ? points[hover] : points[points.length - 1];

  return (
    <div className="viz-root rounded-2xl border p-6" style={{ background: "var(--surface-1)" }}>
      <style>{`
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
      `}</style>

      <div className="mb-4 flex items-baseline justify-between">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]">
            Account equity
          </div>
          <div className="font-mono text-3xl tabular-nums text-[var(--text-primary)]">
            ${active.equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
        </div>
        <div
          className="font-mono text-sm tabular-nums"
          style={{ color: isUp ? "var(--good)" : "var(--critical)" }}
        >
          {isUp ? "▲" : "▼"} ${Math.abs(delta).toLocaleString(undefined, { maximumFractionDigits: 0 })} (
          {deltaPct >= 0 ? "+" : ""}
          {deltaPct.toFixed(2)}%)
        </div>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-56 w-full"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const relX = ((e.clientX - rect.left) / rect.width) * width;
          const idx = Math.round(((relX - padX) / (width - padX * 2)) * (points.length - 1));
          setHover(Math.min(Math.max(idx, 0), points.length - 1));
        }}
      >
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={padX}
            x2={width - padX}
            y1={padY + f * (height - padY * 2)}
            y2={padY + f * (height - padY * 2)}
            stroke="var(--gridline)"
            strokeDasharray="2 4"
            strokeWidth={1}
          />
        ))}

        <path d={path} fill="none" stroke="var(--series-equity)" strokeWidth={2} strokeLinecap="round" />

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

      <div className="mt-2 flex justify-between font-mono text-[10px] text-[var(--muted)]">
        <span>{points[0].label}</span>
        <span>{active.label}</span>
        <span>{points[points.length - 1].label}</span>
      </div>
    </div>
  );
}
