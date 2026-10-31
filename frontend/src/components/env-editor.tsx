"use client";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { ENV_LABEL, type ConfigPatch, type EnvironmentKey, type Flag, type FlagConfig } from "@/lib/types";
import { RolloutBar } from "./flag-parts";
import { TagInput } from "./tag-input";
import { Button } from "./ui/button";
import { Card, CardHeader } from "./ui/feedback";
import { Switch } from "./ui/form";
import { useToast } from "./ui/toast";

const same = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

export function EnvEditor({
  flag,
  env,
  onSaved,
}: {
  flag: Flag;
  env: EnvironmentKey;
  onSaved: (f: Flag) => void;
}) {
  const server: FlagConfig = flag.environments[env];
  const toast = useToast();
  const [enabled, setEnabled] = useState(server.enabled);
  const [kill, setKill] = useState(server.kill_switch);
  const [pct, setPct] = useState(server.rollout_percentage);
  const [included, setIncluded] = useState(server.included_users);
  const [excluded, setExcluded] = useState(server.excluded_users);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patch: ConfigPatch = {};
  if (enabled !== server.enabled) patch.enabled = enabled;
  if (kill !== server.kill_switch) patch.kill_switch = kill;
  if (pct !== server.rollout_percentage) patch.rollout_percentage = pct;
  if (!same(included, server.included_users)) patch.included_users = included;
  if (!same(excluded, server.excluded_users)) patch.excluded_users = excluded;
  const dirty = Object.keys(patch).length > 0;
  const archived = flag.archived;

  function discard() {
    setEnabled(server.enabled);
    setKill(server.kill_switch);
    setPct(server.rollout_percentage);
    setIncluded(server.included_users);
    setExcluded(server.excluded_users);
    setError(null);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateConfig(flag.key, env, patch);
      onSaved(updated);
      toast("success", `Saved ${ENV_LABEL[env].toLowerCase()} configuration`);
    } catch (e) {
      setError(e instanceof ApiError ? e.friendly : "Could not save changes");
    } finally {
      setSaving(false);
    }
  }

  const clamp = (n: number) => Math.min(100, Math.max(0, Math.round(Number.isFinite(n) ? n : 0)));

  return (
    <Card data-testid={`editor-${env}`}>
      <CardHeader
        title={`${ENV_LABEL[env]} configuration`}
        subtitle={`Changes apply to ${env} only. Version ${server.version}.`}
        action={dirty ? <span className="rounded-md bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn">Unsaved changes</span> : undefined}
      />
      <div className="divide-y divide-border">
        <div className="flex items-center justify-between gap-4 px-5 py-4">
          <div>
            <p className="text-sm font-medium">Enabled</p>
            <p className="text-xs text-muted">Master switch. When off, nobody receives the feature.</p>
          </div>
          <Switch checked={enabled} onChange={setEnabled} disabled={archived} label={`Enabled in ${env}`} />
        </div>

        <div className="px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Rollout percentage</p>
              <p className="text-xs text-muted">Share of remaining users (after inclusion/exclusion) who receive the feature.</p>
            </div>
            <div className="flex items-center gap-1.5">
              <input
                aria-label="Rollout percentage"
                type="number"
                min={0}
                max={100}
                value={pct}
                disabled={archived}
                onChange={(e) => setPct(clamp(e.target.valueAsNumber))}
                className="h-9 w-16 rounded-lg border border-border-strong bg-surface px-2 text-right font-mono text-sm tabular-nums focus:border-accent focus:ring-2 focus:ring-accent/25 focus:outline-none"
              />
              <span className="text-sm text-muted">%</span>
            </div>
          </div>
          <input
            aria-label="Rollout slider"
            type="range"
            min={0}
            max={100}
            step={1}
            value={pct}
            disabled={archived}
            onChange={(e) => setPct(Number(e.target.value))}
            className="mt-3 w-full"
          />
          <div className="mt-1 flex items-center justify-between">
            <RolloutBar pct={pct} active={enabled && !kill} className="max-w-48" />
            <div className="flex gap-1">
              {[0, 5, 25, 50, 100].map((p) => (
                <button
                  key={p}
                  type="button"
                  disabled={archived}
                  onClick={() => setPct(p)}
                  className="rounded-md px-2 py-0.5 font-mono text-xs text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-50"
                >
                  {p}%
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid gap-5 px-5 py-4 sm:grid-cols-2">
          <div>
            <p className="text-sm font-medium">Always include</p>
            <p className="mb-2 text-xs text-muted">These users always receive the feature (unless excluded).</p>
            <TagInput label="Included users" values={included} onChange={setIncluded} placeholder="user id, press Enter" />
          </div>
          <div>
            <p className="text-sm font-medium">Always exclude</p>
            <p className="mb-2 text-xs text-muted">These users never receive the feature. Beats inclusion.</p>
            <TagInput label="Excluded users" values={excluded} onChange={setExcluded} placeholder="user id, press Enter" />
          </div>
        </div>

        <div className="flex items-center justify-between gap-4 bg-danger-soft/40 px-5 py-4">
          <div>
            <p className="text-sm font-medium text-danger">Emergency kill switch</p>
            <p className="text-xs text-muted">Overrides everything, including inclusion lists. Use when a release goes wrong.</p>
          </div>
          <Switch checked={kill} onChange={setKill} tone="danger" disabled={archived} label={`Kill switch in ${env}`} />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3.5">
        <p role={error ? "alert" : undefined} className={error ? "text-sm text-danger" : "text-xs text-muted"}>
          {error ?? (archived ? "Archived flags are read-only. Restore the flag to edit it." : "Precedence: kill switch → exclude → include → rollout → off.")}
        </p>
        <div className="flex gap-2">
          <Button onClick={discard} disabled={!dirty || saving}>
            Discard
          </Button>
          <Button variant="primary" onClick={save} loading={saving} disabled={!dirty || archived}>
            Save {env === "production" ? "production" : "development"} changes
          </Button>
        </div>
      </div>
    </Card>
  );
}
