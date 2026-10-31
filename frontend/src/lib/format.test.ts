import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { describeEvent, slugify, timeAgo } from "./format";
import type { AuditEvent } from "./types";

const event = (action: string, details: Record<string, unknown>): AuditEvent => ({
  id: "1",
  created_at: "2026-01-01T00:00:00Z",
  actor: "admin",
  action,
  flag_key: "f",
  environment: "development",
  details,
});

describe("slugify", () => {
  it("makes backend-valid keys", () => {
    expect(slugify("New Dashboard!")).toBe("new-dashboard");
    expect(slugify("  --Hello__World--  ")).toBe("hello-world");
    expect(slugify("Ünïcode flag")).toBe("unicode-flag");
    expect(slugify("")).toBe("");
  });
  it("never exceeds 64 chars or ends with a dash", () => {
    const s = slugify("a".repeat(63) + " b");
    expect(s.length).toBeLessThanOrEqual(64);
    expect(s.endsWith("-")).toBe(false);
  });
});

describe("timeAgo", () => {
  const now = Date.parse("2026-01-01T12:00:00Z");
  it("formats relative times", () => {
    expect(timeAgo("2026-01-01T11:59:50Z", now)).toBe("just now");
    expect(timeAgo("2026-01-01T11:30:00Z", now)).toBe("30 minutes ago");
    expect(timeAgo("2025-12-31T12:00:00Z", now)).toBe("yesterday");
  });
});

describe("describeEvent", () => {
  it("summarises rollout and targeting changes", () => {
    expect(describeEvent(event("flag.rollout_changed", { from: 20, to: 50 }))).toBe("Rollout 20% → 50%");
    expect(
      describeEvent(event("flag.targeting_updated", { included_added: ["a"], included_removed: [], excluded_added: [], excluded_removed: ["z"] })),
    ).toBe("included +a · excluded −z");
  });
});

describe("ApiError.friendly", () => {
  it("joins validation details", () => {
    const e = new ApiError(422, "validation_error", "Request validation failed", [{ loc: ["body", "key"], message: "bad key" }]);
    expect(e.friendly).toBe("key: bad key");
  });
  it("falls back to the message", () => {
    expect(new ApiError(409, "conflict", "already exists").friendly).toBe("already exists");
  });
});
