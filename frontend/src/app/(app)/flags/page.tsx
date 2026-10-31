"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/confirm";
import { RolloutBar } from "@/components/flag-parts";
import { NewFlagDialog } from "@/components/new-flag-dialog";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Input, Switch } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { absoluteTime, timeAgo } from "@/lib/format";
import { ENVIRONMENTS, ENV_LABEL, type EnvironmentKey, type Flag } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

function EnvCell({ flag, env, onToggle, busy }: { flag: Flag; env: EnvironmentKey; onToggle: (v: boolean) => void; busy: boolean }) {
  const c = flag.environments[env];
  return (
    <div className="min-w-0" data-testid={`cell-${flag.key}-${env}`}>
      <div className="mb-1 flex items-center justify-between gap-2 md:hidden">
        <span className="text-xs font-medium text-muted">{ENV_LABEL[env]}</span>
      </div>
      <div className="flex items-center gap-3">
        <Switch
          checked={c.enabled}
          disabled={flag.archived || busy}
          onChange={onToggle}
          label={`${c.enabled ? "Disable" : "Enable"} ${flag.key} in ${env}`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[13px]">
            {c.kill_switch ? (
              <span className="font-medium text-danger">Kill switch</span>
            ) : (
              <span className={cn("font-medium", c.enabled ? "text-ink" : "text-subtle")}>{c.enabled ? "On" : "Off"}</span>
            )}
            <span className="font-mono text-xs text-muted">{c.rollout_percentage}%</span>
          </div>
          <RolloutBar pct={c.rollout_percentage} active={c.enabled && !c.kill_switch} className="mt-1.5 max-w-[120px]" />
        </div>
      </div>
    </div>
  );
}

export default function FlagsPage() {
  const router = useRouter();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ flag: Flag; action: "archive" | "restore" } | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);

  const { data, error, loading, reload, setData } = useFetch(
    () => api.listFlags({ includeArchived: showArchived, search: debounced || undefined }),
    [showArchived, debounced],
  );

  function replace(updated: Flag) {
    if (data) setData({ ...data, items: data.items.map((f) => (f.key === updated.key ? updated : f)) });
  }

  async function toggle(flag: Flag, env: EnvironmentKey, enabled: boolean) {
    setBusyKey(`${flag.key}:${env}`);
    try {
      replace(await api.updateConfig(flag.key, env, { enabled }));
      toast("success", `${flag.name} ${enabled ? "enabled" : "disabled"} in ${ENV_LABEL[env].toLowerCase()}`);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.friendly : "Could not update the flag");
    } finally {
      setBusyKey(null);
    }
  }

  async function runConfirm() {
    if (!confirm) return;
    setBusyKey(confirm.flag.key);
    try {
      if (confirm.action === "archive") await api.archiveFlag(confirm.flag.key);
      else await api.restoreFlag(confirm.flag.key);
      toast("success", `${confirm.flag.name} ${confirm.action === "archive" ? "archived" : "restored"}`);
      setConfirm(null);
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.friendly : "Action failed");
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Feature flags"
        subtitle="Each flag has an independent configuration per environment. Toggle a flag here or open it for rollout and targeting."
        actions={
          <Button variant="primary" onClick={() => setCreating(true)}>
            <span aria-hidden>+</span> New flag
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          type="search"
          aria-label="Search flags"
          placeholder="Search by name or key…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <label className="flex cursor-pointer items-center gap-2 text-[13px] text-muted">
          <Switch checked={showArchived} onChange={setShowArchived} label="Show archived flags" />
          Show archived
        </label>
        {data && <span className="ml-auto text-xs text-muted">{data.total} flag{data.total === 1 ? "" : "s"}</span>}
      </div>

      {error && <ErrorState message={error} onRetry={reload} />}

      {loading && !data && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {data && data.items.length === 0 && !error && (
        <EmptyState
          title={debounced ? "No flags match your search" : "No feature flags yet"}
          body={debounced ? "Try a different name or key." : "Create your first flag to start rolling features out safely."}
          action={!debounced && <Button variant="primary" onClick={() => setCreating(true)}>Create a flag</Button>}
        />
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
          <div className="hidden grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_132px_104px] gap-4 border-b border-border bg-surface-2 px-5 py-2.5 text-[11px] font-semibold tracking-wider text-subtle uppercase md:grid">
            <span>Flag</span>
            <span>Development</span>
            <span>Production</span>
            <span>Last updated</span>
            <span className="text-right">Actions</span>
          </div>
          <ul className="divide-y divide-border">
            {data.items.map((flag) => (
              <li
                key={flag.key}
                data-testid={`flag-row-${flag.key}`}
                className={cn(
                  "grid gap-4 px-5 py-4 transition-colors hover:bg-surface-2/60 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_132px_104px] md:items-center",
                  flag.archived && "opacity-60",
                )}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link href={`/flags/${flag.key}`} className="truncate font-medium hover:underline">
                      {flag.name}
                    </Link>
                    {flag.archived && <Badge>Archived</Badge>}
                  </div>
                  <p className="mt-0.5 truncate font-mono text-xs text-muted">{flag.key}</p>
                </div>
                {ENVIRONMENTS.map((env) => (
                  <EnvCell key={env} flag={flag} env={env} busy={busyKey === `${flag.key}:${env}`} onToggle={(v) => toggle(flag, env, v)} />
                ))}
                <time dateTime={flag.updated_at} title={absoluteTime(flag.updated_at)} className="text-[13px] text-muted">
                  {timeAgo(flag.updated_at)}
                </time>
                <div className="flex justify-start gap-1 md:justify-end">
                  <Button size="sm" onClick={() => router.push(`/flags/${flag.key}`)} aria-label={`Edit ${flag.key}`}>
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirm({ flag, action: flag.archived ? "restore" : "archive" })}
                    aria-label={`${flag.archived ? "Restore" : "Archive"} ${flag.key}`}
                  >
                    {flag.archived ? "Restore" : "Archive"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <NewFlagDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(f) => {
          setCreating(false);
          toast("success", `Created ${f.name}`);
          router.push(`/flags/${f.key}`);
        }}
      />
      <ConfirmDialog
        open={!!confirm}
        title={confirm?.action === "archive" ? `Archive “${confirm.flag.name}”?` : `Restore “${confirm?.flag.name}”?`}
        body={
          confirm?.action === "archive"
            ? "Archived flags always evaluate to off in every environment. You can restore it later."
            : "The flag returns to its previous configuration."
        }
        confirmLabel={confirm?.action === "archive" ? "Archive flag" : "Restore flag"}
        danger={confirm?.action === "archive"}
        busy={busyKey === confirm?.flag.key}
        onConfirm={runConfirm}
        onClose={() => setConfirm(null)}
      />
    </>
  );
}
