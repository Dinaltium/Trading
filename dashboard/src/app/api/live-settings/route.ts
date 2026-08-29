import { NextRequest, NextResponse } from "next/server";

// Server-only route. GITHUB_TOKEN never reaches the client — set it as a Vercel
// environment variable on THIS project only (the private/password-protected admin
// project), never on the public dashboard project. Needs "repo" scope (classic PAT)
// or Contents read/write (fine-grained PAT) on Dinaltium/Trading.
//
// This intentionally only ever writes config/live_settings.json — never touches
// risk_limits.yaml or any other file. See src/live_settings.py's docstring for why
// risk limits specifically stay out of remote reach.

const OWNER = "Dinaltium";
const REPO = "Trading";
const PATH = "config/live_settings.json";
const BRANCH = "main";

const ALLOWED_PROVIDERS = ["groq", "featherless", "mistral"];
const ALLOWED_UNDERLYINGS = ["SPY", "QQQ", "DIA", "IWM"];

type LiveSettings = {
  active_model_provider: string;
  underlyings: string[];
  trading_paused: boolean;
};

function validate(body: unknown): LiveSettings | null {
  if (typeof body !== "object" || body === null) return null;
  const b = body as Record<string, unknown>;

  const provider = b.active_model_provider;
  if (typeof provider !== "string" || !ALLOWED_PROVIDERS.includes(provider)) return null;

  const underlyings = b.underlyings;
  if (
    !Array.isArray(underlyings) ||
    underlyings.length === 0 ||
    !underlyings.every((u) => typeof u === "string" && ALLOWED_UNDERLYINGS.includes(u))
  ) {
    return null;
  }

  const trading_paused = b.trading_paused;
  if (typeof trading_paused !== "boolean") return null;

  return { active_model_provider: provider, underlyings, trading_paused };
}

export async function GET() {
  const res = await fetch(
    `https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}/${PATH}`,
    { cache: "no-store" }
  );
  if (!res.ok) {
    return NextResponse.json(
      { active_model_provider: "groq", underlyings: ["SPY", "QQQ"], trading_paused: false },
      { status: 200 }
    );
  }
  const data = await res.json();
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return NextResponse.json(
      { error: "GITHUB_TOKEN not configured on this deployment" },
      { status: 500 }
    );
  }

  const body = await req.json();
  const settings = validate(body);
  if (!settings) {
    return NextResponse.json({ error: "invalid settings payload" }, { status: 400 });
  }

  const apiUrl = `https://api.github.com/repos/${OWNER}/${REPO}/contents/${PATH}`;

  // Need the current file's sha to update it (GitHub Contents API requirement)
  const currentRes = await fetch(`${apiUrl}?ref=${BRANCH}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" },
    cache: "no-store",
  });
  const currentSha = currentRes.ok ? (await currentRes.json()).sha : undefined;

  const record = {
    ...settings,
    updated_at: new Date().toISOString(),
    updated_by: "admin-dashboard",
  };
  const content = Buffer.from(JSON.stringify(record, null, 2) + "\n").toString("base64");

  const commitRes = await fetch(apiUrl, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message: `live_settings: ${settings.active_model_provider}, ${settings.underlyings.join("/")}, paused=${settings.trading_paused}`,
      content,
      branch: BRANCH,
      ...(currentSha ? { sha: currentSha } : {}),
    }),
  });

  if (!commitRes.ok) {
    const errText = await commitRes.text();
    return NextResponse.json({ error: `GitHub commit failed: ${errText}` }, { status: 502 });
  }

  return NextResponse.json({ ok: true, ...record });
}
