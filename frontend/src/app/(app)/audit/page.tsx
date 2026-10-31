"use client";
import { useEffect, useState } from "react";
import { AuditRow } from "@/components/audit-row";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { api, ApiError } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

const PAGE = 25;

export default function AuditPage() {
  const [flagKey, setFlagKey] = useState("");
  const [extra, setExtra] = useState<AuditEvent[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);

  const flags = useFetch(() => api.listFlags({ includeArchived: true }), []);
  const first = useFetch(() => api.audit({ limit: PAGE, offset: 0, flagKey: flagKey || undefined }), [flagKey]);

  useEffect(() => setExtra([]), [flagKey]);

  const items = [...(first.data?.items ?? []), ...extra];
  const total = first.data?.total ?? 0;

  async function loadMore() {
    setLoadingMore(true);
    setMoreError(null);
    try {
      const next = await api.audit({ limit: PAGE, offset: items.length, flagKey: flagKey || undefined });
      setExtra((e) => [...e, ...next.items]);
    } catch (e) {
      setMoreError(e instanceof ApiError ? e.friendly : "Could not load more events");
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <>
      <PageHeader title="Audit log" subtitle="Every administrative change: who did what, when, and the before/after values." />
      <div className="mb-4 flex items-center gap-3">
        <Select aria-label="Filter by flag" value={flagKey} onChange={(e) => setFlagKey(e.target.value)} className="max-w-xs">
          <option value="">All flags and API keys</option>
          {flags.data?.items.map((f) => (
            <option key={f.key} value={f.key}>
              {f.key}
            </option>
          ))}
        </Select>
        {first.data && <span className="text-xs text-muted">{total} event{total === 1 ? "" : "s"}</span>}
      </div>

      {first.error && <ErrorState message={first.error} onRetry={first.reload} />}
      {first.loading && !first.data && <Skeleton className="h-64 w-full" />}
      {first.data && items.length === 0 && <EmptyState title="No audit events" body="Nothing has been changed for this selection yet." />}
      {items.length > 0 && (
        <Card>
          <ul className="divide-y divide-border">
            {items.map((e) => (
              <AuditRow key={e.id} event={e} />
            ))}
          </ul>
          {items.length < total && (
            <div className="border-t border-border p-3 text-center">
              {moreError && <p role="alert" className="mb-2 text-xs text-danger">{moreError}</p>}
              <Button size="sm" onClick={loadMore} loading={loadingMore}>
                Load more ({total - items.length} remaining)
              </Button>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
