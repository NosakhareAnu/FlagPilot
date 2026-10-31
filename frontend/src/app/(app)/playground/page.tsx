"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EnvTag } from "@/components/flag-parts";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardHeader, Code, EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Input, Segmented, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { REASON_TEXT } from "@/lib/format";
import { ENVIRONMENTS, ENV_LABEL, SAMPLE_USERS, type AdminEvaluation, type EnvironmentKey, type Flag } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

/** Bar from bucket 0 → 9999; green zone = users inside the rollout, marker = this user's bucket. */
function BucketMeter({ bucket, pct }: { bucket: number | null; pct: number }) {
  return (
    <div>
      <div className="relative h-3 rounded-full bg-border" role="img" aria-label={`Bucket ${bucket ?? "n/a"} of 10000, rollout ${pct}%`}>
        <div className="absolute inset-y-0 left-0 rounded-full bg-accent/70" style={{ width: `${pct}%` }} />
        {bucket !== null && (
          <div className="absolute -top-1.5 h-6 w-0.5 rounded bg-ink" style={{ left: `${Math.min(99.6, bucket / 100)}%` }} />
        )}
      </div>
      <div className="mt-2 flex justify-between font-mono text-[11px] text-muted">
        <span>0</span>
        <span>rollout threshold {pct * 100}</span>
        <span>10000</span>
      </div>
    </div>
  );
}

function PlaygroundInner() {
  const params = useSearchParams();
  const toast = useToast();
  const flags = useFetch(() => api.listFlags(), []);
  const [flagKey, setFlagKey] = useState(params.get("flag") ?? "");
  const [env, setEnv] = useState<EnvironmentKey>(params.get("env") === "production" ? "production" : "development");
  const [userId, setUserId] = useState("alice");
  const [result, setResult] = useState<AdminEvaluation | null>(null);
  const [previous, setPrevious] = useState<AdminEvaluation | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [cohort, setCohort] = useState<Record<string, AdminEvaluation>>({});
  const [pctDraft, setPctDraft] = useState<number | null>(null);
  const [applying, setApplying] = useState(false);
  const seq = useRef(0);

  const items = flags.data?.items;
  const flag: Flag | undefined = items?.find((f) => f.key === flagKey);

  // default to the first flag once loaded
  useEffect(() => {
    if (items?.length && !items.some((f) => f.key === flagKey)) setFlagKey(items[0]?.key ?? "");
  }, [items, flagKey]);

  const run = useCallback(
    async (user: string) => {
      if (!flagKey || !user.trim()) return;
      const mine = ++seq.current;
      setEvaluating(true);
      setEvalError(null);
      try {
        const r = await api.evaluate(flagKey, env, user);
        if (mine !== seq.current) return;
        setResult((cur) => {
          if (cur && cur.flag_key === r.flag_key && cur.environment === r.environment) setPrevious(cur);
          else setPrevious(null);
          return r;
        });
        // evaluate the whole sample cohort through the same backend path
        const all = await Promise.all(SAMPLE_USERS.map((u) => api.evaluate(flagKey, env, u.id).then((x) => [u.id, x] as const)));
        if (mine === seq.current) setCohort(Object.fromEntries(all));
      } catch (e) {
        if (mine === seq.current) setEvalError(e instanceof ApiError ? e.friendly : "Evaluation failed");
      } finally {
        if (mine === seq.current) setEvaluating(false);
      }
    },
    [flagKey, env],
  );

  // evaluate automatically when the flag / environment / user changes
  useEffect(() => {
    setPrevious(null);
    void run(userId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flagKey, env]);

  const currentPct = flag?.environments[env].rollout_percentage ?? 0;
  const draft = pctDraft ?? currentPct;
  useEffect(() => setPctDraft(null), [flagKey, env, currentPct]);

  async function applyRollout() {
    if (!flag) return;
    setApplying(true);
    try {
      const updated = await api.updateConfig(flag.key, env, { rollout_percentage: draft });
      flags.setData(flags.data ? { ...flags.data, items: flags.data.items.map((f) => (f.key === updated.key ? updated : f)) } : flags.data);
      toast("success", `Rollout set to ${draft}% in ${ENV_LABEL[env].toLowerCase()}`);
      await run(userId);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.friendly : "Could not change rollout");
    } finally {
      setApplying(false);
    }
  }

  const enabledCount = useMemo(() => Object.values(cohort).filter((c) => c.enabled).length, [cohort]);
  const changed = previous && result && previous.enabled !== result.enabled;

  return (
    <>
      <PageHeader
        title="Evaluation playground"
        subtitle="Runs the real evaluation engine on the backend (same code path and Redis cache as the public API). Change the rollout, then re-evaluate."
      />

      {flags.error && <ErrorState message={flags.error} onRetry={flags.reload} />}
      {flags.loading && !items && <Skeleton className="h-72 w-full" />}
      {items && items.length === 0 && (
        <EmptyState title="Nothing to evaluate yet" body="Create a feature flag first, then come back to test who receives it." />
      )}

      {items && items.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
          <div className="space-y-6">
            <Card>
              <CardHeader title="1 · Choose what to evaluate" />
              <div className="space-y-4 p-5">
                <Field label="Feature flag">
                  {(id) => (
                    <Select id={id} value={flagKey} onChange={(e) => setFlagKey(e.target.value)}>
                      {items.map((f) => (
                        <option key={f.key} value={f.key}>
                          {f.name} ({f.key})
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                <div className="space-y-1.5">
                  <span className="block text-[13px] font-medium">Environment</span>
                  <Segmented label="Environment" value={env} onChange={setEnv} options={ENVIRONMENTS.map((e) => ({ value: e, label: ENV_LABEL[e] }))} />
                </div>
                <Field label="User identifier">
                  {(id) => (
                    <form
                      className="flex gap-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void run(userId);
                      }}
                    >
                      <Input id={id} value={userId} maxLength={256} className="font-mono" onChange={(e) => setUserId(e.target.value)} placeholder="user-1842" />
                      <Button type="submit" variant="primary" loading={evaluating} disabled={!userId.trim()}>
                        Evaluate
                      </Button>
                    </form>
                  )}
                </Field>
                <div>
                  <p className="mb-2 text-xs text-muted">Sample users</p>
                  <div className="flex flex-wrap gap-1.5">
                    {SAMPLE_USERS.map((u) => (
                      <button
                        key={u.id}
                        type="button"
                        title={u.note}
                        onClick={() => {
                          setUserId(u.id);
                          void run(u.id);
                        }}
                        className={cn(
                          "rounded-full border px-3 py-1 text-[13px] transition-colors",
                          userId === u.id ? "border-accent bg-accent-soft text-accent-ink" : "border-border-strong hover:bg-surface-2",
                        )}
                      >
                        {u.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </Card>

            {flag && (
              <Card>
                <CardHeader title="2 · Change the rollout" subtitle={`${ENV_LABEL[env]} · applies immediately via the admin API`} />
                <div className="space-y-4 p-5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted">Rollout percentage</span>
                    <span className="font-mono tabular-nums" data-testid="playground-pct">
                      {draft}%
                    </span>
                  </div>
                  <input
                    aria-label="Playground rollout slider"
                    type="range"
                    min={0}
                    max={100}
                    value={draft}
                    onChange={(e) => setPctDraft(Number(e.target.value))}
                    className="w-full"
                  />
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs text-muted">
                      {flag.environments[env].enabled ? "Flag is enabled" : "Flag is disabled in this environment"} · currently {currentPct}%
                    </p>
                    <Button variant="primary" size="sm" onClick={applyRollout} loading={applying} disabled={draft === currentPct || flag.archived}>
                      Apply & re-evaluate
                    </Button>
                  </div>
                </div>
              </Card>
            )}
          </div>

          <div className="space-y-6">
            {evalError && <ErrorState message={evalError} onRetry={() => run(userId)} />}
            <Card data-testid="result-card">
              <CardHeader
                title="Result"
                subtitle={result ? `${result.flag_key} · ${ENV_LABEL[result.environment]} · user “${userId}”` : undefined}
                action={result && <EnvTag env={result.environment} />}
              />
              {!result ? (
                <div className="p-5">
                  <Skeleton className="h-32 w-full" />
                </div>
              ) : (
                <div className="space-y-5 p-5">
                  <div className="flex flex-wrap items-center gap-4">
                    <div
                      data-testid="result-enabled"
                      className={cn(
                        "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-lg font-semibold",
                        result.enabled ? "bg-accent-soft text-accent-ink" : "bg-surface-2 text-muted",
                      )}
                    >
                      <span className={cn("h-2.5 w-2.5 rounded-full", result.enabled ? "bg-accent" : "bg-subtle")} />
                      {result.enabled ? "Feature ENABLED" : "Feature DISABLED"}
                    </div>
                    <div>
                      <Badge tone={result.enabled ? "good" : "neutral"}>
                        <span data-testid="result-reason">{result.reason}</span>
                      </Badge>
                      {changed && (
                        <Badge tone="warn" className="ml-2">
                          changed since last evaluation
                        </Badge>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-muted">
                    <strong className="text-ink">{REASON_TEXT[result.reason].title}.</strong> {REASON_TEXT[result.reason].body}
                  </p>

                  {result.bucket !== null && (
                    <div>
                      <p className="mb-2 text-[13px] font-medium">
                        Bucket <Code>{result.bucket}</Code> of 10000 · rollout {result.rollout_percentage ?? 0}%
                      </p>
                      <BucketMeter bucket={result.bucket} pct={result.rollout_percentage ?? 0} />
                      <p className="mt-2 text-xs text-muted">
                        bucket = SHA-256(flag ⏐ environment ⏐ user) mod 10000. The user is inside the rollout when bucket &lt; percentage × 100.
                      </p>
                    </div>
                  )}
                  <p className="text-xs text-subtle">
                    Served from <strong>{result.source === "cache" ? "Redis cache" : result.source === "database" ? "PostgreSQL (cache miss, now cached)" : "PostgreSQL (cache unavailable)"}</strong>
                  </p>
                </div>
              )}
            </Card>

            <Card>
              <CardHeader
                title="Sample cohort"
                subtitle={`${enabledCount} of ${SAMPLE_USERS.length} sample users receive this feature`}
              />
              <ul className="grid gap-px bg-border sm:grid-cols-2" data-testid="cohort">
                {SAMPLE_USERS.map((u) => {
                  const c = cohort[u.id];
                  return (
                    <li key={u.id} className="flex items-center justify-between gap-3 bg-surface px-5 py-2.5">
                      <div className="min-w-0">
                        <p className="text-[13.5px] font-medium">{u.label}</p>
                        <p className="truncate text-xs text-muted">{u.note}</p>
                      </div>
                      {c ? (
                        <div className="text-right">
                          <Badge tone={c.enabled ? "good" : "neutral"} className="justify-center">
                            {c.enabled ? "on" : "off"}
                          </Badge>
                          <p className="mt-0.5 font-mono text-[11px] text-subtle">{c.reason}</p>
                        </div>
                      ) : (
                        <Skeleton className="h-8 w-16" />
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

export default function PlaygroundPage() {
  return (
    <Suspense>
      <PlaygroundInner />
    </Suspense>
  );
}
