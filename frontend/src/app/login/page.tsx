"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { api, ApiError, setCsrfToken } from "@/lib/api";

function safeNext(raw: string | null): string {
  // only same-origin absolute paths; blocks open redirects such as //evil.com or https://evil.com
  return raw && raw.startsWith("/") && !raw.startsWith("//") && !raw.startsWith("/login") ? raw : "/";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await api.login(email.trim(), password);
      setCsrfToken(session.csrf_token);
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setError("Incorrect email or password.");
      else if (err instanceof ApiError && err.status === 429) setError("Too many sign-in attempts. Wait a minute and try again.");
      else if (err instanceof ApiError) setError(err.friendly);
      else setError("Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <Field label="Email">
        {(id) => (
          <Input id={id} type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@flagpilot.local" />
        )}
      </Field>
      <Field label="Password">
        {(id) => (
          <Input id={id} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        )}
      </Field>
      {error && (
        <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      <Button type="submit" variant="primary" className="w-full" loading={busy} disabled={!email || !password}>
        Sign in
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-[#0e1f1d] p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="8" fill="#2dd4bf" />
            <path d="M10 25V7h12l-2.5 5L22 17H10" fill="none" stroke="#0e1f1d" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="text-[15px] font-semibold tracking-tight">FlagPilot</span>
        </div>
        <div className="max-w-md">
          <h1 className="text-4xl leading-[1.1] font-semibold tracking-tight">Ship behind a flag.<br />Release when you are ready.</h1>
          <p className="mt-4 text-[15px] leading-relaxed text-white/70">
            Roll features out to 5% of users, target your testers, and pull the plug without redeploying anything.
          </p>
          <dl className="mt-10 space-y-4 text-sm">
            {[
              ["Deterministic rollouts", "SHA-256 bucketing: the same user always gets the same answer."],
              ["Independent environments", "Enable in development, keep production dark."],
              ["Instant kill switch", "Cache invalidation makes changes effective immediately."],
            ].map(([t, d]) => (
              <div key={t} className="flex gap-3">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#2dd4bf]" />
                <div>
                  <dt className="font-medium">{t}</dt>
                  <dd className="text-white/60">{d}</dd>
                </div>
              </div>
            ))}
          </dl>
        </div>
        <p className="font-mono text-xs text-white/40">POST /api/v1/evaluate → {"{ enabled: true, reason: \"percentage_rollout\" }"}</p>
      </section>

      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
          <p className="mt-1 mb-6 text-sm text-muted">Use the demo administrator account from your local <code className="font-mono text-xs">.env</code> file.</p>
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
      </section>
    </main>
  );
}
