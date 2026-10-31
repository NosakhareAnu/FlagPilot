import type { AuditEvent, Reason } from "./types";

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function timeAgo(iso: string, now: number = Date.now()): string {
  const diff = (new Date(iso).getTime() - now) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return "just now";
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
    ["week", 604800],
    ["month", 2592000],
    ["year", 31536000],
  ];
  let chosen: [Intl.RelativeTimeFormatUnit, number] = ["minute", 60];
  for (const u of units) if (abs >= u[1]) chosen = u;
  return rtf.format(Math.round(diff / chosen[1]), chosen[0]);
}

export function absoluteTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "medium" });
}

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/\p{M}/gu, "") // strip combining accents left by NFKD
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
    .replace(/-+$/g, "");
}

export const REASON_TEXT: Record<Reason, { title: string; body: string }> = {
  flag_disabled: { title: "Flag disabled", body: "The flag is switched off in this environment, so nobody receives it." },
  kill_switch: { title: "Kill switch active", body: "The emergency kill switch overrides every other rule. Nobody receives the feature." },
  user_excluded: { title: "User excluded", body: "This user is on the exclusion list. Exclusion beats inclusion and the rollout percentage." },
  user_included: { title: "User included", body: "This user is on the inclusion list, so they receive the feature regardless of the rollout percentage." },
  percentage_rollout: { title: "Inside the rollout", body: "The user's deterministic bucket falls inside the current rollout percentage." },
  default_disabled: { title: "Outside the rollout", body: "No rule matched and the user's bucket is outside the rollout percentage, so the default (off) applies." },
  flag_archived: { title: "Flag archived", body: "Archived flags always evaluate to off." },
  flag_not_found: { title: "Unknown flag", body: "No flag with this key exists in the environment. The safe default (off) is returned." },
};

function list(v: unknown): string[] {
  return Array.isArray(v) ? (v as string[]) : [];
}

export const ACTION_LABEL: Record<string, string> = {
  "flag.created": "Flag created",
  "flag.updated": "Details edited",
  "flag.enabled": "Enabled",
  "flag.disabled": "Disabled",
  "flag.rollout_changed": "Rollout changed",
  "flag.targeting_updated": "Targeting updated",
  "flag.kill_switch_activated": "Kill switch activated",
  "flag.kill_switch_cleared": "Kill switch cleared",
  "flag.archived": "Flag archived",
  "flag.restored": "Flag restored",
  "api_key.created": "API key created",
  "api_key.revoked": "API key revoked",
};

export type Tone = "neutral" | "good" | "warn" | "danger" | "info";

export function actionTone(action: string): Tone {
  if (action === "flag.enabled" || action === "flag.created" || action === "flag.restored") return "good";
  if (action === "flag.kill_switch_activated" || action === "flag.archived" || action === "api_key.revoked") return "danger";
  if (action === "flag.rollout_changed" || action === "flag.targeting_updated") return "info";
  if (action === "flag.kill_switch_cleared") return "warn";
  return "neutral";
}

/** One-line human summary of an audit event's details. */
export function describeEvent(e: AuditEvent): string {
  const d = e.details;
  switch (e.action) {
    case "flag.rollout_changed":
      return `Rollout ${d.from}% → ${d.to}%`;
    case "flag.targeting_updated": {
      const parts: string[] = [];
      const ia = list(d.included_added), ir = list(d.included_removed), ea = list(d.excluded_added), er = list(d.excluded_removed);
      if (ia.length) parts.push(`included +${ia.join(", ")}`);
      if (ir.length) parts.push(`included −${ir.join(", ")}`);
      if (ea.length) parts.push(`excluded +${ea.join(", ")}`);
      if (er.length) parts.push(`excluded −${er.join(", ")}`);
      return parts.join(" · ") || "Targeting lists updated";
    }
    case "flag.updated": {
      const changes = (d.changes ?? {}) as Record<string, { from: string; to: string }>;
      return Object.entries(changes)
        .map(([k, v]) => `${k}: “${v.from}” → “${v.to}”`)
        .join(" · ");
    }
    case "flag.created":
      return String(d.name ?? "");
    case "api_key.created":
    case "api_key.revoked":
      return `${d.name} (${d.key_prefix}…)`;
    default:
      return "";
  }
}
