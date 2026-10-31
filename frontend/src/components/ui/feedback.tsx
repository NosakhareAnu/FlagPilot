import { cn } from "@/lib/cn";
import type { Tone } from "@/lib/format";
import type { HTMLAttributes, ReactNode } from "react";
import { Button } from "./button";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted border-border",
  good: "bg-accent-soft text-accent-ink border-transparent",
  warn: "bg-warn-soft text-warn border-transparent",
  danger: "bg-danger-soft text-danger border-transparent",
  info: "bg-info-soft text-info border-transparent",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}

export function Dot({ on, tone }: { on: boolean; tone?: "danger" }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block h-2 w-2 rounded-full", tone === "danger" ? "bg-danger" : on ? "bg-accent" : "bg-border-strong")}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} aria-hidden />;
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border-strong px-6 py-14 text-center">
      <div className="mb-3 grid h-10 w-10 place-items-center rounded-full bg-surface-2 text-subtle">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M5 21V4m0 0h11l-2 4 2 4H5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <p className="font-medium">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-muted">{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-4 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger"
    >
      <span>{message}</span>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLElement>) {
  return (
    <section className={cn("rounded-xl border border-border bg-surface shadow-card", className)} {...rest}>
      {children}
    </section>
  );
}

export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-3.5">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[12px] text-ink">{children}</code>;
}
