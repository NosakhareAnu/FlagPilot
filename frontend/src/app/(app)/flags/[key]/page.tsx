"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AuditRow } from "@/components/audit-row";
import { ConfirmDialog } from "@/components/confirm";
import { EnvEditor } from "@/components/env-editor";
import { StatusBadge } from "@/components/flag-parts";
import { PageHeader } from "@/components/page-header";
import { Button, buttonClass } from "@/components/ui/button";
import { Badge, Card, CardHeader, EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Input, Segmented, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { absoluteTime, timeAgo } from "@/lib/format";
import { ENVIRONMENTS, ENV_LABEL, type EnvironmentKey, type Flag } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

function Details({ flag, onSaved }: { flag: Flag; onSaved: (f: Flag) => void }) {
  const toast = useToast();
  const [name, setName] = useState(flag.name);
  const [description, setDescription] = useState(flag.description);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = name.trim() !== flag.name || description.trim() !== flag.description;

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateFlag(flag.key, { name: name.trim(), description: description.trim() });
      onSaved(updated);
      toast("success", "Details saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.friendly : "Could not save details");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Details" />
      <form onSubmit={save} className="space-y-4 p-5" noValidate>
        <Field label="Name" error={error}>
          {(id) => <Input id={id} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} disabled={flag.archived} />}
        </Field>
        <Field label="Description">
          {(id) => <Textarea id={id} value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} disabled={flag.archived} />}
        </Field>
        <Button type="submit" variant="primary" size="sm" loading={saving} disabled={!dirty || !name.trim()}>
          Save details
        </Button>
      </form>
    </Card>
  );
}

export default function FlagEditorPage() {
  const { key } = useParams<{ key: string }>();
  const toast = useToast();
  const { data: flag, error, loading, reload, setData } = useFetch(() => api.getFlag(key), [key]);
  const history = useFetch(() => api.audit({ limit: 6, flagKey: key }), [key, flag?.updated_at]);
  const [env, setEnv] = useState<EnvironmentKey>("development");
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [busy, setBusy] = useState(false);

  async function toggleArchive() {
    if (!flag) return;
    setBusy(true);
    try {
      const updated = flag.archived ? await api.restoreFlag(flag.key) : await api.archiveFlag(flag.key);
      setData(updated);
      toast("success", flag.archived ? "Flag restored" : "Flag archived");
      setConfirmArchive(false);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.friendly : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (error && !flag) {
    return (
      <>
        <Link href="/flags" className="mb-4 inline-block text-sm text-muted hover:text-ink">← All flags</Link>
        <ErrorState message={error} onRetry={reload} />
      </>
    );
  }
  if (loading && !flag) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (!flag) return null;

  return (
    <>
      <Link href="/flags" className="mb-3 inline-block text-sm text-muted hover:text-ink">
        ← All flags
      </Link>
      <PageHeader
        title={flag.name}
        subtitle={flag.description || undefined}
        actions={
          <>
            <Link href={`/playground?flag=${flag.key}&env=${env}`} className={buttonClass("secondary")}>
              Test in playground
            </Link>
          </>
        }
      />
      <div className="-mt-3 mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px] text-muted">
        <code className="rounded bg-surface-2 px-2 py-0.5 font-mono text-xs text-ink" data-testid="flag-key">
          {flag.key}
        </code>
        {flag.archived && <Badge tone="warn">Archived</Badge>}
        {ENVIRONMENTS.map((e) => (
          <span key={e} className="inline-flex items-center gap-1.5">
            {ENV_LABEL[e]} <StatusBadge config={flag.environments[e]} />
          </span>
        ))}
        <span title={absoluteTime(flag.updated_at)}>Last updated {timeAgo(flag.updated_at)}</span>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <Segmented
            label="Environment"
            value={env}
            onChange={setEnv}
            options={ENVIRONMENTS.map((e) => ({ value: e, label: ENV_LABEL[e] }))}
          />
          {/* keyed so local form state resets whenever the saved version changes */}
          <EnvEditor key={`${env}-${flag.environments[env].version}-${flag.archived}`} flag={flag} env={env} onSaved={setData} />
        </div>

        <div className="space-y-6">
          <Details key={`${flag.name}-${flag.description}`} flag={flag} onSaved={setData} />
          <Card>
            <CardHeader title="History" subtitle="Most recent changes to this flag" />
            {history.data && history.data.items.length === 0 ? (
              <div className="p-5">
                <EmptyState title="No history" body="Changes will appear here." />
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {history.data?.items.map((e) => <AuditRow key={e.id} event={e} showFlag={false} />)}
              </ul>
            )}
            {history.data && history.data.total > history.data.items.length && (
              <div className="border-t border-border px-5 py-2.5 text-center">
                <Link href="/audit" className="text-xs font-medium text-accent hover:underline">
                  View full audit log
                </Link>
              </div>
            )}
          </Card>
          <Card>
            <CardHeader title={flag.archived ? "Restore flag" : "Archive flag"} />
            <div className="flex items-center justify-between gap-4 p-5">
              <p className="text-sm text-muted">
                {flag.archived
                  ? "Archived flags evaluate to off everywhere. Restore it to edit its configuration again."
                  : "Archived flags evaluate to off in every environment. This can be undone."}
              </p>
              <Button variant={flag.archived ? "secondary" : "danger"} size="sm" onClick={() => setConfirmArchive(true)}>
                {flag.archived ? "Restore" : "Archive"}
              </Button>
            </div>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={confirmArchive}
        title={flag.archived ? `Restore “${flag.name}”?` : `Archive “${flag.name}”?`}
        body={flag.archived ? "The flag becomes editable again with its previous configuration." : "It will immediately evaluate to off for all users."}
        confirmLabel={flag.archived ? "Restore flag" : "Archive flag"}
        danger={!flag.archived}
        busy={busy}
        onConfirm={toggleArchive}
        onClose={() => setConfirmArchive(false)}
      />
    </>
  );
}
