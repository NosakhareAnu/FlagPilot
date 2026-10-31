"use client";
import { cn } from "@/lib/cn";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type ToastKind = "success" | "error";
interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}
const Ctx = createContext<{ toast: (kind: ToastKind, message: string) => void }>({ toast: () => {} });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const toast = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, kind, message }]);
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), kind === "error" ? 7000 : 3500);
  }, []);
  const value = useMemo(() => ({ toast }), [toast]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {items.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            className={cn(
              "pop pointer-events-auto flex max-w-md items-center gap-2 rounded-lg border px-4 py-2.5 text-sm shadow-[var(--shadow-lg)]",
              t.kind === "success" ? "border-accent/30 bg-surface text-ink" : "border-danger/30 bg-danger-soft text-danger",
            )}
          >
            <span className={cn("h-2 w-2 rounded-full", t.kind === "success" ? "bg-accent" : "bg-danger")} />
            {t.message}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx).toast;
