import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

/**
 * Server-side proxy used by the demo app. It plays the role of a customer's backend:
 * the environment API key lives ONLY in this server process (never sent to the browser) and only
 * the demo flags can be evaluated, so the public demo page cannot be used to probe other flags.
 */
const DEMO_FLAGS = new Set(["new-dashboard", "dark-mode", "ai-insights"]);
const BACKEND = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

interface EvalResponse {
  flag_key: string;
  enabled: boolean;
  reason: string;
  environment: string;
}

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams;
  const env = q.get("env") === "production" ? "production" : "development";
  const user = q.get("user") ?? "";
  const flags = (q.get("flags") ?? "").split(",").filter(Boolean);

  if (!/^[\w.@-]{1,64}$/.test(user)) return NextResponse.json({ error: "invalid user" }, { status: 400 });
  if (!flags.length || flags.some((f) => !DEMO_FLAGS.has(f))) return NextResponse.json({ error: "unknown demo flag" }, { status: 400 });

  const key = env === "production" ? process.env.DEMO_API_KEY_PRODUCTION : process.env.DEMO_API_KEY_DEVELOPMENT;
  if (!key) return NextResponse.json({ error: "demo API key is not configured" }, { status: 503 });

  try {
    const results = await Promise.all(
      flags.map(async (flag_key) => {
        const res = await fetch(`${BACKEND}/api/v1/evaluate`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
          body: JSON.stringify({ flag_key, user_id: user }),
          cache: "no-store",
          signal: AbortSignal.timeout(3000),
        });
        if (!res.ok) throw new Error(`evaluate returned ${res.status}`);
        return (await res.json()) as EvalResponse;
      }),
    );
    return NextResponse.json({
      environment: env,
      user,
      results: Object.fromEntries(results.map((r) => [r.flag_key, { enabled: r.enabled, reason: r.reason }])),
    });
  } catch {
    // Fail closed: the demo UI falls back to the legacy experience.
    return NextResponse.json({ error: "FlagPilot evaluation unavailable" }, { status: 502 });
  }
}
