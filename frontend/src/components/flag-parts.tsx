import { cn } from "@/lib/cn";
import type { FlagConfig } from "@/lib/types";
import { Badge, Dot } from "./ui/feedback";

export function RolloutBar({ pct, active = true, className }: { pct: number; active?: boolean; className?: string }) {
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-border", className)}
      role="img"
      aria-label={`${pct}% rollout`}
    >
      <div className={cn("h-full rounded-full transition-all", active ? "bg-accent" : "bg-subtle")} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function statusOf(c: FlagConfig): { label: string; tone: "good" | "neutral" | "danger" } {
  if (c.kill_switch) return { label: "Killed", tone: "danger" };
  return c.enabled ? { label: "On", tone: "good" } : { label: "Off", tone: "neutral" };
}

export function StatusBadge({ config }: { config: FlagConfig }) {
  const s = statusOf(config);
  return (
    <Badge tone={s.tone}>
      <Dot on={config.enabled && !config.kill_switch} tone={config.kill_switch ? "danger" : undefined} />
      {s.label}
    </Badge>
  );
}

export function EnvTag({ env }: { env: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[11px] font-medium",
        env === "production" ? "bg-warn-soft text-warn" : "bg-info-soft text-info",
      )}
    >
      {env === "production" ? "prod" : "dev"}
    </span>
  );
}
