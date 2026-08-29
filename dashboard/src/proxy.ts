import { NextRequest, NextResponse } from "next/server";

// Gates /admin and /api/live-settings behind a shared password — the public "/"
// dashboard route is untouched by this file and stays completely open, which is
// the point: judges need zero-friction access to "/", only the two of you need
// access to the settings toggle.
//
// Set ADMIN_PASSWORD as a Vercel environment variable on this project. It's read
// server-side only inside middleware, never sent to the client.

const PROTECTED_PREFIXES = ["/admin", "/api/live-settings"];
const COOKIE_NAME = "admin_auth";

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (!PROTECTED_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const expected = process.env.ADMIN_PASSWORD;
  if (!expected) {
    // Fails closed: if the password isn't configured on this deployment, admin
    // routes are unreachable rather than silently open.
    return new NextResponse("Admin routes not configured on this deployment.", { status: 503 });
  }

  const cookie = req.cookies.get(COOKIE_NAME)?.value;
  if (cookie === expected) {
    return NextResponse.next();
  }

  // Basic Auth prompt — browser handles the login UI natively, no custom form needed.
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Basic ")) {
    const decoded = atob(authHeader.slice(6));
    const [, password] = decoded.split(":");
    if (password === expected) {
      const res = NextResponse.next();
      res.cookies.set(COOKIE_NAME, expected, { httpOnly: true, secure: true, sameSite: "strict", maxAge: 60 * 60 * 24 * 7 });
      return res;
    }
  }

  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Admin"' },
  });
}

export const config = {
  matcher: ["/admin/:path*", "/api/live-settings/:path*"],
};
