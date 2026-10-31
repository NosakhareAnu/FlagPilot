import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  primary: "bg-ink text-bg hover:opacity-90 disabled:opacity-40",
  secondary: "bg-surface text-ink border border-border-strong hover:bg-surface-2 disabled:opacity-50",
  ghost: "text-muted hover:text-ink hover:bg-surface-2 disabled:opacity-50",
  danger: "bg-danger text-white hover:opacity-90 disabled:opacity-40",
};
const sizes: Record<Size, string> = { sm: "h-8 px-3 text-[13px]", md: "h-9 px-4 text-sm" };

export function buttonClass(variant: Variant = "secondary", size: Size = "md", extra?: string) {
  return cn(
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed",
    variants[variant],
    sizes[size],
    extra,
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  className,
  loading,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean }) {
  return (
    <button type="button" className={buttonClass(variant, size, className)} disabled={disabled || loading} {...rest}>
      {loading && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cn("h-4 w-4 animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
