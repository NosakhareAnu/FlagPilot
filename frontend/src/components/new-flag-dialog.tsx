"use client";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { slugify } from "@/lib/format";
import type { Flag } from "@/lib/types";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";
import { Field, Input, Textarea } from "./ui/form";

export function NewFlagDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (f: Flag) => void }) {
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [keyTouched, setKeyTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [keyError, setKeyError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function reset() {
    setName("");
    setKey("");
    setKeyTouched(false);
    setDescription("");
    setError(null);
    setKeyError(null);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setKeyError(null);
    try {
      const flag = await api.createFlag({ key, name: name.trim(), description: description.trim() });
      reset();
      onCreated(flag);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setKeyError(err.message);
      else if (err instanceof ApiError && err.code === "validation_error" && err.details?.some((d) => d.loc.includes("key")))
        setKeyError("Use lowercase letters, digits, '-' or '_' (1–64 chars, starting and ending with a letter or digit).");
      else setError(err instanceof ApiError ? err.friendly : "Could not create the flag.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="New feature flag"
      description="Flags start disabled at 0% in both environments."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Name">
          {(id) => (
            <Input
              id={id}
              value={name}
              autoFocus
              maxLength={120}
              placeholder="New dashboard"
              onChange={(e) => {
                setName(e.target.value);
                if (!keyTouched) setKey(slugify(e.target.value));
              }}
            />
          )}
        </Field>
        <Field label="Key" hint="Used by your code and the evaluation API. Cannot be changed later." error={keyError}>
          {(id) => (
            <Input
              id={id}
              value={key}
              maxLength={64}
              className="font-mono"
              placeholder="new-dashboard"
              onChange={(e) => {
                setKeyTouched(true);
                setKey(e.target.value);
              }}
            />
          )}
        </Field>
        <Field label="Description" hint="Optional.">
          {(id) => <Textarea id={id} value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} />}
        </Field>
        {error && (
          <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <Button
            onClick={() => {
              reset();
              onClose();
            }}
          >
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={busy} disabled={!name.trim() || !key}>
            Create flag
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
