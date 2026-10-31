import type {
  AdminEvaluation,
  ApiKey,
  ApiKeyCreated,
  AuditList,
  ConfigPatch,
  EnvironmentKey,
  Flag,
  FlagList,
  Session,
  Stats,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: { loc: string[]; message: string }[],
  ) {
    super(message);
  }

  /** Human-readable text including field-level validation problems. */
  get friendly(): string {
    if (this.code === "validation_error" && this.details?.length) {
      return this.details.map((d) => `${d.loc.filter((p) => p !== "body").join(".")}: ${d.message}`).join("; ");
    }
    return this.message;
  }
}

let csrfToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

async function request<T>(method: string, path: string, body?: unknown, opts: { skip401?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the FlagPilot API. Check that the backend is running.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error;
    if (res.status === 401 && !opts.skip401) onUnauthorized?.();
    throw new ApiError(res.status, err?.code ?? "http_error", err?.message ?? `Request failed (${res.status})`, err?.details);
  }
  return data as T;
}

const A = "/api/v1/admin";

export const api = {
  login: (email: string, password: string) =>
    request<Session>("POST", "/api/v1/auth/login", { email, password }, { skip401: true }),
  me: () => request<Session>("GET", "/api/v1/auth/me", undefined, { skip401: true }),
  logout: () => request<void>("POST", "/api/v1/auth/logout"),

  stats: () => request<Stats>("GET", `${A}/stats`),
  listFlags: (params: { includeArchived?: boolean; search?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.includeArchived) q.set("include_archived", "true");
    if (params.search) q.set("search", params.search);
    return request<FlagList>("GET", `${A}/flags?${q}`);
  },
  getFlag: (key: string) => request<Flag>("GET", `${A}/flags/${encodeURIComponent(key)}`),
  createFlag: (data: { key: string; name: string; description: string }) => request<Flag>("POST", `${A}/flags`, data),
  updateFlag: (key: string, data: { name?: string; description?: string }) =>
    request<Flag>("PATCH", `${A}/flags/${encodeURIComponent(key)}`, data),
  updateConfig: (key: string, environment: EnvironmentKey, patch: ConfigPatch) =>
    request<Flag>("PATCH", `${A}/flags/${encodeURIComponent(key)}/environments/${environment}`, patch),
  archiveFlag: (key: string) => request<Flag>("POST", `${A}/flags/${encodeURIComponent(key)}/archive`),
  restoreFlag: (key: string) => request<Flag>("POST", `${A}/flags/${encodeURIComponent(key)}/restore`),

  evaluate: (flag_key: string, environment: EnvironmentKey, user_id: string) =>
    request<AdminEvaluation>("POST", `${A}/evaluate`, { flag_key, environment, user_id }),

  audit: (params: { limit?: number; offset?: number; flagKey?: string } = {}) => {
    const q = new URLSearchParams({ limit: String(params.limit ?? 25), offset: String(params.offset ?? 0) });
    if (params.flagKey) q.set("flag_key", params.flagKey);
    return request<AuditList>("GET", `${A}/audit?${q}`);
  },

  listKeys: () => request<ApiKey[]>("GET", `${A}/api-keys`),
  createKey: (name: string, environment: EnvironmentKey) =>
    request<ApiKeyCreated>("POST", `${A}/api-keys`, { name, environment }),
  revokeKey: (id: string) => request<ApiKey>("DELETE", `${A}/api-keys/${id}`),
};
