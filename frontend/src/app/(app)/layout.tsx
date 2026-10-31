"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/feedback";
import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider, useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";

const NAV = [
  { href: "/", label: "Overview", icon: "M3 12l9-8 9 8M5 10v10h14V10" },
  { href: "/flags", label: "Feature flags", icon: "M5 21V4m0 0h11l-2 4 2 4H5" },
  { href: "/playground", label: "Playground", icon: "M8 5v14l11-7z" },
  { href: "/audit", label: "Audit log", icon: "M4 6h16M4 12h16M4 18h10" },
  { href: "/api-keys", label: "API keys", icon: "M15 7a4 4 0 1 1-3.9 4.9L4 19v-3h3v-3h3l1.1-1.1A4 4 0 0 1 15 7z" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { email, loading, signOut } = useAuth();
  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="w-64 space-y-3">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[236px_1fr]">
      <aside className="border-b border-border bg-surface lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between px-5 py-4 lg:py-5">
          <Logo />
          <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[11px] font-medium text-muted lg:hidden">{email}</span>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-1 lg:flex-col lg:overflow-visible lg:pb-0">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={active(n.href) ? "page" : undefined}
              className={cn(
                "flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors",
                active(n.href) ? "bg-accent-soft text-accent-ink" : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              <Icon d={n.icon} />
              {n.label}
            </Link>
          ))}
          <div className="hidden px-3 pt-5 pb-1 text-[11px] font-semibold tracking-wider text-subtle uppercase lg:block">Resources</div>
          <a href="/demo" target="_blank" rel="noreferrer" className="flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-medium text-muted hover:bg-surface-2 hover:text-ink">
            <Icon d="M14 4h6v6M20 4l-9 9M10 6H5v13h13v-5" />
            Demo app
          </a>
          <a href={process.env.NEXT_PUBLIC_API_DOCS_URL ?? "http://localhost:8000/docs"} target="_blank" rel="noreferrer" className="flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-medium text-muted hover:bg-surface-2 hover:text-ink">
            <Icon d="M8 4h8l4 4v12H8zM16 4v4h4M11 13h6M11 17h6" />
            API docs
          </a>
        </nav>
        <div className="hidden border-t border-border p-4 lg:block">
          <p className="truncate text-xs text-muted" title={email ?? ""}>
            {email}
          </p>
          <Button variant="ghost" size="sm" className="mt-2 -ml-3" onClick={signOut}>
            Sign out
          </Button>
        </div>
      </aside>
      <main className="min-w-0 px-5 py-6 sm:px-8 lg:py-8">
        <div className="mx-auto max-w-6xl">{children}</div>
        <div className="mt-10 flex justify-center lg:hidden">
          <Button variant="ghost" size="sm" onClick={signOut}>
            Sign out
          </Button>
        </div>
      </main>
    </div>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>
        <Shell>{children}</Shell>
      </ToastProvider>
    </AuthProvider>
  );
}
