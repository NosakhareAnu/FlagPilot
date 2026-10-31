"use client";
import Link from "next/link";
import { AuditRow } from "@/components/audit-row";
import { RolloutBar } from "@/components/flag-parts";
import { PageHeader } from "@/components/page-header";
import { buttonClass } from "@/components/ui/button";
import { Card, CardHeader, EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { api } from "@/lib/api";
import { ENVIRONMENTS, ENV_LABEL } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <Card className="p-5">
      <p className="text-[13px] text-muted">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, "-")}`}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-subtle">{hint}</p>}
    </Card>
  );
}

export default function OverviewPage() {
  const { data, error, loading, reload } = useFetch(() => api.stats(), []);

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Live numbers from your flag configuration and audit history."
        actions={
          <>
            <Link href="/playground" className={buttonClass("secondary")}>
              Open playground
            </Link>
            <Link href="/flags" className={buttonClass("primary")}>
              Manage flags
            </Link>
          </>
        }
      />

      {error && <ErrorState message={error} onRetry={reload} />}

      {loading && !data && (
        <div className="grid gap-4 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {data && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Total flags" value={data.total_flags} hint={`${data.archived_flags} archived`} />
            <Stat label="Active flags" value={data.active_flags} hint="Not archived" />
            <Stat
              label="Enabled in production"
              value={data.environments.production.enabled}
              hint={`${data.environments.production.disabled} disabled`}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
            <Card>
              <CardHeader title="Enabled vs disabled" subtitle="Active flags per environment" />
              <div className="space-y-5 p-5">
                {ENVIRONMENTS.map((env) => {
                  const s = data.environments[env];
                  const total = s.enabled + s.disabled;
                  return (
                    <div key={env} data-testid={`env-${env}`}>
                      <div className="mb-2 flex items-baseline justify-between text-[13px]">
                        <span className="font-medium">{ENV_LABEL[env]}</span>
                        <span className="text-muted tabular-nums">
                          <strong className="text-ink">{s.enabled}</strong> enabled · {s.disabled} disabled
                        </span>
                      </div>
                      <RolloutBar pct={total ? Math.round((s.enabled / total) * 100) : 0} />
                    </div>
                  );
                })}
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Recent configuration changes"
                action={
                  <Link href="/audit" className="text-xs font-medium text-accent hover:underline">
                    View all
                  </Link>
                }
              />
              {data.recent_events.length === 0 ? (
                <div className="p-5">
                  <EmptyState title="No changes yet" body="Changes to flags will appear here as they happen." />
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {data.recent_events.map((e) => (
                    <AuditRow key={e.id} event={e} />
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
