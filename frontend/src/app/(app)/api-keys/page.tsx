"use client";
import { useState, type FormEvent } from "react";
import { ConfirmDialog } from "@/components/confirm";
import { EnvTag } from "@/components/flag-parts";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Badge, Card, CardHeader, Code, EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Input, Segmented } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { absoluteTime, timeAgo } from "@/lib/format";
import type { ApiKey, ApiKeyCreated, EnvironmentKey } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

export default function ApiKeysPage() {
  const toast = useToast();
  const { data, error, loading, reload } = useFetch(() => api.listKeys(), []);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [env, setEnv] = useState<EnvironmentKey>("development");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);
  const [copied, setCopied] = useState(false);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const key = await api.createKey(name.trim(), env);
      setCreated(key);
      setCreating(false);
      setName("");
      reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.friendly : "Could not create the key");
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!revoking) return;
    setBusy(true);
    try {
      await api.revokeKey(revoking.id);
      toast("success", `Revoked ${revoking.name}`);
      setRevoking(null);
      reload();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.friendly : "Could not revoke the key");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="API keys"
        subtitle="Evaluation clients authenticate with an environment-scoped key. A development key can never read production configuration."
        actions={
          <Button variant="primary" onClick={() => setCreating(true)}>
            <span aria-hidden>+</span> New key
          </Button>
        }
      />

      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton className="h-40 w-full" />}
      {data && data.length === 0 && <EmptyState title="No API keys" body="Create a key to call the evaluation API from your application." />}
      {data && data.length > 0 && (
        <Card>
          <ul className="divide-y divide-border">
            {data.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5" data-testid="api-key-row">
                <div className="min-w-0 flex-1 basis-56">
                  <p className="flex items-center gap-2 font-medium">
                    {k.name} <EnvTag env={k.environment} />
                    {k.revoked_at && <Badge tone="danger">Revoked</Badge>}
                  </p>
                  <p className="mt-0.5 font-mono text-xs text-muted">{k.key_prefix}…</p>
                </div>
                <time dateTime={k.created_at} title={absoluteTime(k.created_at)} className="text-xs text-muted">
                  Created {timeAgo(k.created_at)}
                </time>
                {!k.revoked_at && (
                  <Button size="sm" variant="ghost" onClick={() => setRevoking(k)}>
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="mt-6">
        <CardHeader title="Using a key" subtitle="Keep keys on your server. Never ship them to browsers or mobile apps." />
        <pre className="overflow-x-auto p-5 font-mono text-[12.5px] leading-relaxed">{`curl -X POST http://localhost:8000/api/v1/evaluate \\
  -H "Authorization: Bearer fpk_development_…" \\
  -H "Content-Type: application/json" \\
  -d '{"flag_key": "new-dashboard", "user_id": "user-1842"}'

# → {"flag_key":"new-dashboard","enabled":true,"reason":"percentage_rollout","environment":"development"}`}</pre>
      </Card>

      <Dialog open={creating} onClose={() => setCreating(false)} title="New API key" description="The secret is shown once. Only its hash is stored.">
        <form onSubmit={create} className="space-y-4" noValidate>
          <Field label="Name" error={formError}>
            {(id) => <Input id={id} autoFocus value={name} maxLength={80} placeholder="Checkout service" onChange={(e) => setName(e.target.value)} />}
          </Field>
          <div className="space-y-1.5">
            <span className="block text-[13px] font-medium">Environment</span>
            <Segmented
              label="Environment"
              value={env}
              onChange={setEnv}
              options={[
                { value: "development", label: "Development" },
                { value: "production", label: "Production" },
              ]}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setCreating(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!name.trim()}>
              Create key
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog open={!!created} onClose={() => { setCreated(null); setCopied(false); }} title="Copy your new key" description="This is the only time the full key is shown.">
        <div className="space-y-4">
          <div className="rounded-lg border border-border-strong bg-surface-2 p-3">
            <Code>{created?.key}</Code>
          </div>
          <div className="flex justify-end gap-2">
            <Button
              onClick={async () => {
                await navigator.clipboard.writeText(created?.key ?? "");
                setCopied(true);
              }}
            >
              {copied ? "Copied ✓" : "Copy key"}
            </Button>
            <Button variant="primary" onClick={() => { setCreated(null); setCopied(false); }}>
              Done
            </Button>
          </div>
        </div>
      </Dialog>

      <ConfirmDialog
        open={!!revoking}
        title={`Revoke “${revoking?.name}”?`}
        body="Applications using this key will immediately start receiving 401 errors."
        confirmLabel="Revoke key"
        danger
        busy={busy}
        onConfirm={revoke}
        onClose={() => setRevoking(null)}
      />
    </>
  );
}
