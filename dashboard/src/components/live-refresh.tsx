"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

// The page is a server component reading audit_log.jsonl fresh on every request, so it was
// already never stale — but only at the moment you asked for it. A cycle lands every 15
// minutes and the page had no way to notice, which meant the equity figure on screen was
// whatever it had been when you last hit reload.
//
// router.refresh() re-runs the server component and patches the new data into the existing
// tree: no full page load, no lost scroll position, no flash. Polling is paused entirely
// while the tab is hidden and fires once immediately on return, so a tab left open
// overnight costs nothing and is correct the instant it is looked at.
const POLL_MS = 60_000;

export function LiveRefresh() {
  const router = useRouter();
  const [lastUpdate, setLastUpdate] = useState<number>(() => Date.now());
  const [ago, setAgo] = useState(0);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;

    const refresh = () => {
      router.refresh();
      setLastUpdate(Date.now());
    };

    const start = () => {
      stop();
      timer = setInterval(refresh, POLL_MS);
    };

    const stop = () => {
      if (timer) clearInterval(timer);
      timer = undefined;
    };

    const onVisibility = () => {
      if (document.hidden) {
        stop();
      } else {
        refresh();
        start();
      }
    };

    start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [router]);

  // Ticks the "Ns ago" readout independently of the poll, so the label stays honest
  // between refreshes rather than freezing at 0.
  useEffect(() => {
    const t = setInterval(() => setAgo(Math.floor((Date.now() - lastUpdate) / 1000)), 1000);
    return () => clearInterval(t);
  }, [lastUpdate]);

  const label = ago < 60 ? `${ago}s ago` : `${Math.floor(ago / 60)}m ago`;

  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
      <span className="relative inline-flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#0ca30c] opacity-60 motion-reduce:animate-none" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#0ca30c]" />
      </span>
      live · {label}
    </span>
  );
}
