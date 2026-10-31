export type EnvironmentKey = "development" | "production";
export const ENVIRONMENTS: EnvironmentKey[] = ["development", "production"];
export const ENV_LABEL: Record<EnvironmentKey, string> = { development: "Development", production: "Production" };

export type Reason =
  | "flag_disabled"
  | "kill_switch"
  | "user_excluded"
  | "user_included"
  | "percentage_rollout"
  | "default_disabled"
  | "flag_archived"
  | "flag_not_found";

export interface FlagConfig {
  environment: EnvironmentKey;
  enabled: boolean;
  kill_switch: boolean;
  rollout_percentage: number;
  included_users: string[];
  excluded_users: string[];
  version: number;
  updated_at: string;
}

export interface Flag {
  key: string;
  name: string;
  description: string;
  archived: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  environments: Record<EnvironmentKey, FlagConfig>;
}

export interface FlagList {
  items: Flag[];
  total: number;
}

export interface ConfigPatch {
  enabled?: boolean;
  kill_switch?: boolean;
  rollout_percentage?: number;
  included_users?: string[];
  excluded_users?: string[];
}

export interface AuditEvent {
  id: string;
  created_at: string;
  actor: string;
  action: string;
  flag_key: string | null;
  environment: EnvironmentKey | null;
  details: Record<string, unknown>;
}

export interface AuditList {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface Stats {
  total_flags: number;
  active_flags: number;
  archived_flags: number;
  environments: Record<EnvironmentKey, { enabled: number; disabled: number }>;
  recent_events: AuditEvent[];
}

export interface ApiKey {
  id: string;
  name: string;
  environment: EnvironmentKey;
  key_prefix: string;
  created_at: string;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  key: string;
}

export interface AdminEvaluation {
  flag_key: string;
  enabled: boolean;
  reason: Reason;
  environment: EnvironmentKey;
  bucket: number | null;
  rollout_percentage: number | null;
  source: "cache" | "database" | "database_cache_unavailable";
}

export interface Session {
  email: string;
  csrf_token: string;
}

export const SAMPLE_USERS = [
  { id: "alice", label: "Alice", note: "internal tester" },
  { id: "bob", label: "Bob", note: "beta customer" },
  { id: "carol", label: "Carol", note: "new signup" },
  { id: "dave", label: "Dave", note: "enterprise admin" },
  { id: "erin", label: "Erin", note: "free plan" },
  { id: "frank", label: "Frank", note: "agency partner" },
  { id: "grace", label: "Grace", note: "power user" },
  { id: "heidi", label: "Heidi", note: "trial user" },
] as const;
