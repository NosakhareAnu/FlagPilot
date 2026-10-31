"use client";
import { useState, type KeyboardEvent } from "react";

export function TagInput({
  label,
  values,
  onChange,
  placeholder,
  max = 500,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  max?: number;
}) {
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  function commit(raw: string) {
    const parts = raw.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    if (!parts.length) return;
    const next = [...values];
    for (const p of parts) {
      if (p.length > 256) {
        setMsg("User identifiers are limited to 256 characters.");
        return;
      }
      if (!next.includes(p)) next.push(p);
    }
    if (next.length > max) {
      setMsg(`At most ${max} users per list.`);
      return;
    }
    setMsg(null);
    onChange(next);
    setDraft("");
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit(draft);
    } else if (e.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div>
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-lg border border-border-strong bg-surface px-2 py-1.5 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/25">
        {values.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-md bg-surface-2 py-0.5 pr-1 pl-2 font-mono text-xs">
            {v}
            <button
              type="button"
              aria-label={`Remove ${v} from ${label}`}
              className="grid h-4 w-4 place-items-center rounded text-muted hover:bg-border hover:text-ink"
              onClick={() => onChange(values.filter((x) => x !== v))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          aria-label={label}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          onBlur={() => commit(draft)}
          placeholder={values.length ? "" : placeholder}
          className="min-w-24 flex-1 bg-transparent px-1 py-0.5 text-sm outline-none placeholder:text-subtle"
        />
      </div>
      {msg && (
        <p role="alert" className="mt-1 text-xs text-danger">
          {msg}
        </p>
      )}
    </div>
  );
}
