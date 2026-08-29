"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";

// This route only exists on the private, password-protected admin Vercel project —
// never the public dashboard. Deliberately does NOT expose anything from risk_limits.yaml;
// see src/live_settings.py's docstring for why risk limits stay out of remote reach.

const PROVIDERS = [
  { value: "groq", label: "Groq" },
  { value: "featherless", label: "Featherless" },
  { value: "mistral", label: "Mistral" },
];
const UNDERLYINGS = ["SPY", "QQQ", "DIA", "IWM"];

type Settings = {
  active_model_provider: string;
  underlyings: string[];
  trading_paused: boolean;
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
            This provider&apos;s decisions execute real (paper) trades. Every other
            provider automatically becomes shadow-only. Claude Code CLI always stays
            shadow-only regardless of this setting.
          </p>
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
          <CardTitle className="font-mono text-sm">Trading paused</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Switch
            checked={settings.trading_paused}
            onCheckedChange={(checked) => setSettings({ ...settings, trading_paused: checked })}
          />
          <span className="font-mono text-sm text-muted-foreground">
            {settings.trading_paused ? "Paused — scheduler skips every cycle" : "Running normally"}
          </span>
        </CardContent>
      </Card>

      <Button onClick={save} disabled={saving} className="font-mono">
        {saving ? "Saving…" : "Save settings"}
      </Button>
      {status && <p className="font-mono text-xs text-muted-foreground">{status}</p>}
    </div>
  );
}
