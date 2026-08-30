"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";

// This route only exists on the private, password-protected admin Vercel project —
// never the public dashboard. Deliberately does NOT expose anything from risk_limits.yaml;
// see src/live_settings.py's docstring for why risk limits stay out of remote reach.

const PROVIDERS = [
  { value: "groq", label: "Groq", transport: "http" },
  { value: "featherless", label: "Featherless", transport: "http" },
  { value: "mistral", label: "Mistral", transport: "http" },
  // Subprocess, not HTTP: needs the `claude` binary on PATH. Present on a dev laptop,
  // absent on the GitHub Actions runner - hence the warning rendered below.
  { value: "claude_code_cli", label: "Claude Code CLI", transport: "subprocess" },
];
const UNDERLYINGS = ["SPY", "QQQ", "DIA", "IWM"];

// Three states, because "stop everything" is the wrong tool while positions are open —
// it halts new risk and halts managing existing risk at the same time.
const MODES = [
  { value: "running", label: "Running", detail: "Opens new positions and manages existing ones." },
  { value: "exit_only", label: "Exit only", detail: "No new positions. Stop-losses still evaluate and can close." },
  { value: "paused", label: "Paused", detail: "Nothing at all — open positions are left unmanaged." },
];

type Settings = {
  active_model_provider: string;
  underlyings: string[];
  trading_mode: string;
};

export default function AdminPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/live-settings", { cache: "no-store" })
      .then((r) => r.json())
      .then(setSettings)
      .catch(() => setStatus("Failed to load current settings."));
  }, []);

  async function save() {
    if (!settings) return;
    setSaving(true);
    setStatus(null);
    try {
      const res = await fetch("/api/live-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "unknown error");
      setStatus("Saved — the scheduler picks this up on its next tick.");
    } catch (e) {
      setStatus(`Failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  if (!settings) {
    return <div className="p-6 font-mono text-sm text-muted-foreground">Loading current settings…</div>;
  }

  return (
    <div className="mx-auto max-w-xl space-y-6 p-6">
      <header className="space-y-1">
        <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
          Private — not linked from the public dashboard
        </div>
        <h1 className="font-mono text-2xl font-semibold tracking-tight">Live Settings</h1>
        <p className="text-sm text-muted-foreground">
          Changes here affect the live trading loop on the next scheduler tick. Risk
          limits (max loss, drawdown halt, Kelly fraction) are NOT configurable here —
          those stay in <code className="font-mono">risk_limits.yaml</code>, hand-edited only.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-sm">Active model provider</CardTitle>
        </CardHeader>
        <CardContent>
          <Select
            value={settings.active_model_provider}
            onValueChange={(v) => v && setSettings({ ...settings, active_model_provider: v })}
          >
            <SelectTrigger className="w-full font-mono">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PROVIDERS.map((p) => (
                <SelectItem key={p.value} value={p.value} className="font-mono">
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="mt-2 text-xs text-muted-foreground">
            This provider&apos;s decisions execute real (paper) trades. The other three
            automatically become shadow-only for the same cycle.
          </p>
          {settings.active_model_provider === "claude_code_cli" && (
            <p className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-400">
              Claude Code CLI runs as a subprocess and needs the <code className="font-mono">claude</code>{" "}
              binary on PATH. The GitHub Actions runner does not have it — selected there, every
              cycle fails with &ldquo;&apos;claude&apos; CLI not found on PATH&rdquo;, no decision is
              produced and nothing trades. Use this only when the loop runs on a machine that has
              the CLI installed and authenticated.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-sm">Underlyings in scope</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {UNDERLYINGS.map((u) => (
            <label key={u} className="flex items-center gap-2 font-mono text-sm">
              <Checkbox
                checked={settings.underlyings.includes(u)}
                onCheckedChange={(checked) => {
                  const next = checked
                    ? [...settings.underlyings, u]
                    : settings.underlyings.filter((x) => x !== u);
                  if (next.length > 0) setSettings({ ...settings, underlyings: next });
                }}
              />
              {u}
            </label>
          ))}
          <p className="pt-1 text-xs text-muted-foreground">
            SPY/QQQ/DIA/IWM are index ETFs — no single-company earnings risk, no
            earnings-calendar data needed. At least one must stay checked.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-sm">Trading mode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {MODES.map((m) => (
            <label
              key={m.value}
              className="flex cursor-pointer items-start gap-3 rounded-md border p-3 has-[:checked]:border-foreground/40 has-[:checked]:bg-muted/40"
            >
              <input
                type="radio"
                name="trading_mode"
                value={m.value}
                checked={settings.trading_mode === m.value}
                onChange={() => setSettings({ ...settings, trading_mode: m.value })}
                className="mt-1"
              />
              <span>
                <span className="block font-mono text-sm">{m.label}</span>
                <span className="block text-xs text-muted-foreground">{m.detail}</span>
              </span>
            </label>
          ))}
          {settings.trading_mode === "paused" && (
            <p className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-400">
              Paused also stops stop-loss evaluation. If anything is open, nothing is watching it.
              Prefer <strong>Exit only</strong> unless you specifically want the agent fully idle.
            </p>
          )}
        </CardContent>
      </Card>

      <Button onClick={save} disabled={saving} className="font-mono">
        {saving ? "Saving…" : "Save settings"}
      </Button>
      {status && <p className="font-mono text-xs text-muted-foreground">{status}</p>}
    </div>
  );
}
