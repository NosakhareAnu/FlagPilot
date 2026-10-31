"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Badge, Code } from "@/components/ui/feedback";
import { Segmented, Select } from "@/components/ui/form";
import { cn } from "@/lib/cn";
import { SAMPLE_USERS, type EnvironmentKey } from "@/lib/types";

const FLAGS = ["new-dashboard", "dark-mode", "ai-insights"] as const;
type FlagState = Record<string, { enabled: boolean; reason: string }>;

const KPIS = [
  { label: "Active users", value: "12,480", delta: "+8.2%" },
  { label: "Conversion", value: "3.84%", delta: "+0.4%" },
  { label: "Avg. session", value: "6m 12s", delta: "+11%" },
];
const POINTS = [12, 18, 15, 24, 22, 31, 29, 38, 35, 46, 44, 58];

function Sparkline({ dark }: { dark: boolean }) {
  const max = Math.max(...POINTS);
  const pts = POINTS.map((p, i) => `${(i / (POINTS.length - 1)) * 300},${70 - (p / max) * 62}`).join(" ");
  return (
    <svg viewBox="0 0 300 76" className="h-24 w-full" aria-hidden>
      <polyline fill="none" stroke={dark ? "#2dd4bf" : "#0f766e"} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" points={pts} />
      <polyline fill={dark ? "rgba(45,212,191,.14)" : "rgba(15,118,110,.10)"} stroke="none" points={`0,76 ${pts} 300,76`} />
    </svg>
  );
}

function LegacyDashboard({ dark }: { dark: boolean }) {
  return (
    <div data-testid="legacy-dashboard">
      <h3 className="mb-3 text-lg font-semibold">Dashboard</h3>
      <table className={cn("w-full text-left text-sm", dark ? "text-zinc-200" : "text-zinc-800")}>
        <tbody>
          {KPIS.map((k) => (
            <tr key={k.label} className={cn("border-b", dark ? "border-zinc-700" : "border-zinc-200")}>
              <td className="py-2 pr-4 text-zinc-500">{k.label}</td>
              <td className="py-2 font-medium">{k.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-4 text-xs text-zinc-500">Classic dashboard (flag off)</p>
    </div>
  );
}

function NewDashboard({ dark }: { dark: boolean }) {
  return (
    <div data-testid="new-dashboard">
      <div className="mb-4 flex items-center gap-2">
        <h3 className="text-lg font-semibold">Dashboard</h3>
        <span className="rounded-full bg-teal-500 px-2 py-0.5 text-[11px] font-semibold text-white">NEW</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {KPIS.map((k) => (
          <div key={k.label} className={cn("rounded-xl border p-4", dark ? "border-zinc-700 bg-zinc-800" : "border-zinc-200 bg-white")}>
            <p className="text-xs text-zinc-500">{k.label}</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight">{k.value}</p>
            <p className="text-xs font-medium text-teal-600">{k.delta}</p>
          </div>
        ))}
      </div>
      <div className={cn("mt-3 rounded-xl border p-4", dark ? "border-zinc-700 bg-zinc-800" : "border-zinc-200 bg-white")}>
        <p className="text-xs text-zinc-500">Weekly active users</p>
        <Sparkline dark={dark} />
      </div>
    </div>
  );
}

export default function DemoPage() {
  const [user, setUser] = useState<string>("alice");
  const [env, setEnv] = useState<EnvironmentKey>("development");
  const [state, setState] = useState<FlagState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [pulse, setPulse] = useState(0);
  const seq = useRef(0);

  const refresh = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const res = await fetch(`/demo-api/evaluate?flags=${FLAGS.join(",")}&user=${encodeURIComponent(user)}&env=${env}`, { cache: "no-store" });
      const body = await res.json();
      if (mine !== seq.current) return;
      if (!res.ok) throw new Error(body?.error ?? "evaluation failed");
      setState(body.results);
      setError(null);
      setCheckedAt(new Date());
      setPulse((p) => p + 1);
    } catch (e) {
      if (mine !== seq.current) return;
      setState(null); // fail closed: every feature off
      setError(e instanceof Error ? e.message : "evaluation failed");
    }
  }, [user, env]);

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 2500); // pick up flag changes without a page reload
    return () => clearInterval(t);
  }, [refresh]);

  const on = (flag: string) => state?.[flag]?.enabled === true;
  const dark = on("dark-mode");

  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-5 py-3">
          <Logo />
          <div className="flex items-center gap-3 text-sm">
            <Badge tone="info">Demo app</Badge>
            <Link href="/" className="text-muted hover:text-ink">
              Open dashboard →
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-5 py-8">
        <section>
          <h1 className="text-2xl font-semibold tracking-tight">Acme Analytics: a product controlled by FlagPilot</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            This fictional app asks FlagPilot&apos;s evaluation API which features the signed-in user should see. Open the FlagPilot dashboard in another
            tab, change a flag or its rollout, and watch this page update within a few seconds, with no redeploy.
          </p>
        </section>

        <section className="flex flex-wrap items-end gap-x-6 gap-y-3 rounded-xl border border-border bg-surface p-4">
          <label className="block text-[13px] font-medium">
            Signed in as
            <Select aria-label="Signed in user" value={user} onChange={(e) => setUser(e.target.value)} className="mt-1 w-44">
              {SAMPLE_USERS.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.label} · {u.note}
                </option>
              ))}
            </Select>
          </label>
          <div>
            <span className="block text-[13px] font-medium">App environment</span>
            <div className="mt-1">
              <Segmented
                label="Demo environment"
                value={env}
                onChange={setEnv}
                options={[
                  { value: "development", label: "Development" },
                  { value: "production", label: "Production" },
                ]}
              />
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted">
            <span className="flex items-center gap-1.5" aria-live="polite">
              <span key={pulse} className={cn("h-2 w-2 rounded-full", error ? "bg-danger" : "bg-accent", !error && "pop")} />
              {error ? "FlagPilot unreachable: features off" : checkedAt ? `Checked ${checkedAt.toLocaleTimeString()}` : "Checking…"}
            </span>
            <Button size="sm" onClick={refresh}>
              Refresh
            </Button>
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <section
            className={cn("overflow-hidden rounded-2xl border shadow-card transition-colors", dark ? "border-zinc-700 bg-zinc-900 text-zinc-100" : "border-zinc-200 bg-zinc-50 text-zinc-900")}
            aria-label="Demo application preview"
          >
            <div className={cn("flex items-center gap-1.5 border-b px-4 py-2.5", dark ? "border-zinc-700 bg-zinc-800" : "border-zinc-200 bg-white")}>
              <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
              <span className="h-2.5 w-2.5 rounded-full bg-green-400" />
              <span className="ml-3 text-xs text-zinc-500">acme-analytics.example/{user}</span>
            </div>
            <div className="space-y-5 p-6" data-testid="demo-app" data-dark={dark}>
              {on("new-dashboard") ? <NewDashboard dark={dark} /> : <LegacyDashboard dark={dark} />}
              {on("ai-insights") && (
                <div
                  data-testid="ai-insights-panel"
                  className={cn("rounded-xl border p-4", dark ? "border-indigo-500/40 bg-indigo-500/10" : "border-indigo-200 bg-indigo-50")}
                >
                  <p className="text-sm font-semibold">✨ AI insights</p>
                  <p className="mt-1 text-sm text-zinc-500">Conversion rose 0.4% after Tuesday&apos;s release. Largest gain: returning visitors.</p>
                </div>
              )}
            </div>
          </section>

          <aside className="space-y-4">
            <div className="rounded-xl border border-border bg-surface p-4">
              <h2 className="text-sm font-semibold">What this page asked FlagPilot</h2>
              <ul className="mt-3 space-y-3" data-testid="demo-evaluations">
                {FLAGS.map((f) => {
                  const r = state?.[f];
                  return (
                    <li key={f} className="text-[13px]">
                      <div className="flex items-center justify-between gap-2">
                        <Code>{f}</Code>
                        <Badge tone={r?.enabled ? "good" : "neutral"}>{r ? (r.enabled ? "enabled" : "disabled") : "…"}</Badge>
                      </div>
                      <p className="mt-1 font-mono text-[11.5px] text-muted">reason: {r?.reason ?? "n/a"}</p>
                    </li>
                  );
                })}
              </ul>
              <p className="mt-4 text-xs text-muted">
                Each call is <Code>POST /api/v1/evaluate</Code> with the <strong>{env}</strong> API key, made server-side so the key never reaches your browser.
              </p>
            </div>
            <div className="rounded-xl border border-border bg-surface p-4 text-[13px] text-muted">
              <p className="font-medium text-ink">Try it</p>
              <ol className="mt-2 list-decimal space-y-1 pl-4">
                <li>Open the dashboard → Feature flags → <em>New analytics dashboard</em>.</li>
                <li>Raise the development rollout to 100%.</li>
                <li>Come back: the new dashboard appears. Flip the kill switch and it disappears again.</li>
              </ol>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
