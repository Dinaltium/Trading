"use client";

import { useRef, useState } from "react";

// The model's own account of the figures above it, fetched on demand rather than on load.
// On demand for three reasons: it costs a call, this URL is public, and — the one that
// actually decides it — the page's guarantee is that everything on it is derived from the
// audit record. Model prose is the exception, so the reader should have to ask for it and
// should be told what they are looking at when it arrives.
type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; text: string; model: string }
  | { kind: "error"; message: string };

export function ModelBriefing() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (state.kind === "ready") return; // already fetched this page load

    setState({ kind: "loading" });
    try {
      const res = await fetch("/api/explain");
      const data = await res.json();
      if (!res.ok) {
        setState({ kind: "error", message: data?.error ?? "Something went wrong." });
        return;
      }
      setState({ kind: "ready", text: data.text, model: data.model });
    } catch {
      setState({ kind: "error", message: "Could not reach the briefing endpoint." });
    }
  }

  return (
    <div className="rounded-xl border border-[var(--brand-olive)]/35">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="model-briefing-body"
        className="flex w-full items-center justify-between gap-4 rounded-xl px-5 py-4 text-left transition-colors hover:bg-[var(--brand-olive)]/[0.07] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-olive)]"
      >
        <span className="min-w-0">
          <span className="block font-mono text-[11px] uppercase tracking-[0.15em] text-[var(--brand-olive-deep)]">
            Ask the model to explain this
          </span>
          <span className="mt-1 block text-sm text-muted-foreground">
            The live model reads the figures above and says what they mean. Written by the
            model, not computed — expand to read it.
          </span>
        </span>
        <span
          aria-hidden
          className="shrink-0 font-mono text-lg leading-none text-[var(--brand-olive-deep)] transition-transform duration-200 motion-reduce:transition-none"
          style={{ transform: open ? "rotate(45deg)" : "none" }}
        >
          +
        </span>
      </button>

      <div
        id="model-briefing-body"
        ref={box}
        hidden={!open}
        className="border-t border-[var(--brand-olive)]/25 px-5 py-5"
      >
        {state.kind === "loading" && (
          <p className="font-mono text-[11px] uppercase tracking-[0.15em] text-muted-foreground">
            asking the model…
          </p>
        )}

        {state.kind === "error" && (
          <p className="text-sm leading-relaxed text-muted-foreground">
            {state.message} The figures above are unaffected — they are computed from the
            audit log and never depend on this call.
          </p>
        )}

        {state.kind === "ready" && (
          <>
            <div className="space-y-3 text-[0.95rem] leading-relaxed text-foreground/85">
              {state.text
                .split(/\n{2,}/)
                .map((p) => p.trim())
                .filter(Boolean)
                .map((p, i) => (
                  <p key={i}>{p}</p>
                ))}
            </div>
            <p className="mt-4 border-t border-[var(--brand-olive)]/25 pt-3 font-mono text-[10px] uppercase leading-relaxed tracking-[0.12em] text-muted-foreground">
              written by {state.model} · it was handed the computed figures only, never the
              raw log, and cannot do arithmetic of its own
            </p>
          </>
        )}
      </div>
    </div>
  );
}
