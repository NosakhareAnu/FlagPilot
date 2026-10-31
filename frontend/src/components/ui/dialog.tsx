"use client";
import { useEffect, useRef, type ReactNode } from "react";

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="dialog-title"
      className="pop m-auto w-[min(32rem,calc(100vw-2rem))] rounded-2xl border border-border bg-surface p-0 text-ink shadow-[var(--shadow-lg)] backdrop:bg-black/40 backdrop:backdrop-blur-[2px]"
    >
      {open && (
        <div className="p-6">
          <h2 id="dialog-title" className="text-base font-semibold">
            {title}
          </h2>
          {description && <p className="mt-1 text-sm text-muted">{description}</p>}
          <div className="mt-5">{children}</div>
        </div>
      )}
    </dialog>
  );
}
