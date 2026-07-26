/**
 * Content Studio + Measurement dashboard API client.
 */

import { getSession, sessionId, type AdminSession } from "./session";
import type { CacheStats, EventStats, WarmupResult } from "./measure";
import type { PreviewRenderResponse } from "./segment";

export interface KnowledgeDocument {
  source_document: string;
  chunks: number;
  title?: string | null;
  url?: string | null;
  file_type?: string | null;
  indexed_at?: string | null;
}

export interface SearchResult {
  content: string;
  score: number;
  source_document?: string | null;
  url?: string | null;
}

export type AdminCredentials = Omit<AdminSession, "tenant">;

const call = async (
  session: AdminCredentials,
  path: string,
  init: RequestInit = {},
): Promise<Response> => {
  const response = await fetch(`${session.baseUrl}${path}`, {
    ...init,
    headers: {
      "X-API-Key": session.adminKey,
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body
    }
    throw new Error(detail);
  }

  return response;
};

const request = async (
  session: AdminSession,
  path: string,
  init: RequestInit = {},
): Promise<Response> => {
  const active = getSession();
  if (!active || sessionId(active) !== sessionId(session)) {
    throw new Error(
      `This view is scoped to tenant "${session.tenant}", which is no longer ` +
        "the active session. Reload the page to work on the current tenant.",
    );
  }
  return call(session, path, init);
};

export interface WhoAmI {
  tenant: string;
  is_admin: boolean;
}

export const verifySession = async (
  session: AdminCredentials,
): Promise<WhoAmI> => {
  const response = await call(session, "/api/v1/whoami");
  try {
    const body = (await response.json()) as WhoAmI;
    if (typeof body?.tenant !== "string") throw new Error("no tenant");
    return body;
  } catch {
    throw new Error(
      "That URL answered, but not like a GenUI backend (non-JSON response). " +
        "It looks like a web app, not the API: check the backend URL and port.",
    );
  }
};

export const listDocuments = async (
  session: AdminSession,
): Promise<KnowledgeDocument[]> => {
  const response = await request(session, "/api/v1/documents");
  const body = await response.json();
  return Array.isArray(body?.documents) ? body.documents : [];
};

export const uploadDocument = async (
  session: AdminSession,
  file: File,
): Promise<void> => {
  const form = new FormData();
  form.append("file", file);
  await request(session, "/api/v1/documents/upload", {
    method: "POST",
    body: form,
  });
};

export const deleteDocument = async (
  session: AdminSession,
  sourceDocument: string,
): Promise<void> => {
  await request(
    session,
    `/api/v1/documents/${encodeURIComponent(sourceDocument)}`,
    { method: "DELETE" },
  );
};

export const eventStats = async (
  session: AdminSession,
  zoneId: string,
): Promise<EventStats> => {
  const response = await request(
    session,
    `/api/v1/events/stats?zone_id=${encodeURIComponent(zoneId)}`,
  );
  return (await response.json()) as EventStats;
};

export const zoneCacheStats = async (
  session: AdminSession,
): Promise<CacheStats> => {
  const response = await request(session, "/api/v1/zone/cache/stats");
  return (await response.json()) as CacheStats;
};

export const warmupZones = async (
  session: AdminSession,
  zones: unknown[],
): Promise<WarmupResult> => {
  const response = await request(session, "/api/v1/zone/warmup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zones }),
  });
  return (await response.json()) as WarmupResult;
};

export const renderZone = async (
  session: AdminSession,
  payload: Record<string, unknown>,
): Promise<PreviewRenderResponse> => {
  const response = await request(session, "/api/v1/zone/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await response.json()) as PreviewRenderResponse;
};

export interface ZoneGovernedConfig {
  base_prompt: string;
  context_prompt: string | null;
  pinned_content: Array<Record<string, unknown>>;
  preferred_component_type: string | null;
  max_items: number;
  max_components: number | null;
}

export interface ZoneConfigRecord {
  version: number;
  status: "draft" | "approved";
  config: ZoneGovernedConfig;
  updated_at: string;
}

export interface ZoneListEntry {
  zone_id: string;
  status: "ungoverned" | "draft" | "approved";
  version: number | null;
  updated_at: string | null;
  has_draft: boolean;
  observed: boolean;
}

export interface ZoneListResponse {
  zones: ZoneListEntry[];
  storage: string;
}

export interface ZoneConfigDetail {
  zone_id: string;
  approved: ZoneConfigRecord | null;
  draft: ZoneConfigRecord | null;
  observed: boolean;
}

export interface ZoneWriteResponse {
  zone_id: string;
  record: ZoneConfigRecord;
  storage: string;
}

const CONFIG_BASE = "/api/v1/zone/config";

export const listZoneConfigs = async (
  session: AdminSession,
): Promise<ZoneListResponse> => {
  const response = await request(session, CONFIG_BASE);
  return (await response.json()) as ZoneListResponse;
};

export const getZoneConfig = async (
  session: AdminSession,
  zoneId: string,
): Promise<ZoneConfigDetail> => {
  const response = await request(
    session,
    `${CONFIG_BASE}/${encodeURIComponent(zoneId)}`,
  );
  return (await response.json()) as ZoneConfigDetail;
};

export const saveZoneDraft = async (
  session: AdminSession,
  zoneId: string,
  config: Record<string, unknown>,
  expectedVersion?: number | null,
): Promise<ZoneWriteResponse> => {
  const response = await request(
    session,
    `${CONFIG_BASE}/${encodeURIComponent(zoneId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...config,
        expected_version: expectedVersion ?? null,
      }),
    },
  );
  return (await response.json()) as ZoneWriteResponse;
};

export const approveZoneConfig = async (
  session: AdminSession,
  zoneId: string,
  expectedVersion?: number | null,
): Promise<ZoneWriteResponse> => {
  const response = await request(
    session,
    `${CONFIG_BASE}/${encodeURIComponent(zoneId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion ?? null }),
    },
  );
  return (await response.json()) as ZoneWriteResponse;
};

export const discardZoneDraft = async (
  session: AdminSession,
  zoneId: string,
): Promise<void> => {
  await request(session, `${CONFIG_BASE}/${encodeURIComponent(zoneId)}/draft`, {
    method: "DELETE",
  });
};

export const deleteZoneConfig = async (
  session: AdminSession,
  zoneId: string,
): Promise<void> => {
  await request(session, `${CONFIG_BASE}/${encodeURIComponent(zoneId)}`, {
    method: "DELETE",
  });
};

export interface AuditEntry {
  ts?: string;
  event?: string;
  tenant?: string;
  user_id?: string | null;
  key?: string;
  zone_id?: string;
  page?: string | null;
  render_id?: string;
  arm?: string;
  cache?: {
    status?: string;
    strategy?: string;
    segment?: string;
    age_seconds?: number;
  };
  personalization_applied?: boolean;
  component_types?: string[];
  shown_titles?: string[];
  shown_links?: string[];
  sanitization?: {
    removed_urls?: string[];
    dropped_components?: unknown[];
    removed_numbers?: unknown[];
    policy_violations?: unknown[];
  } | null;
  [key: string]: unknown;
}

export interface AuditQueryParams {
  user_id?: string;
  zone_id?: string;
  event?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface AuditQueryResponse {
  source: string;
  queryable: boolean;
  note: string;
  entries: AuditEntry[];
  has_more: boolean;
}

export const queryAudit = async (
  session: AdminSession,
  params: AuditQueryParams = {},
): Promise<AuditQueryResponse> => {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") qs.set(key, String(value));
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const response = await request(session, `/api/v1/audit${suffix}`);
  return (await response.json()) as AuditQueryResponse;
};

export interface ContentPolicyResponse {
  banned_terms: string[];
  env_terms: string[];
  storage: string;
}

export const getContentPolicy = async (
  session: AdminSession,
): Promise<ContentPolicyResponse> => {
  const response = await request(session, "/api/v1/content-policy");
  return (await response.json()) as ContentPolicyResponse;
};

export const saveContentPolicy = async (
  session: AdminSession,
  bannedTerms: string[],
): Promise<ContentPolicyResponse> => {
  const response = await request(session, "/api/v1/content-policy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ banned_terms: bannedTerms }),
  });
  return (await response.json()) as ContentPolicyResponse;
};

export interface TenantThemeResponse {
  theme: Record<string, string> | null;
  updated_at: string | null;
}

export interface TenantThemeWriteResponse {
  theme: Record<string, string>;
  updated_at: string;
  storage: string;
}

export const getTenantTheme = async (
  session: AdminSession,
): Promise<TenantThemeResponse> => {
  const response = await request(session, "/api/v1/theme");
  return (await response.json()) as TenantThemeResponse;
};

export const saveTenantTheme = async (
  session: AdminSession,
  theme: Record<string, string>,
): Promise<TenantThemeWriteResponse> => {
  const response = await request(session, "/api/v1/theme", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme }),
  });
  return (await response.json()) as TenantThemeWriteResponse;
};

export interface BackendHealth {
  status?: string;
  llm?: string;
  redis?: string;
}

export const backendHealth = async (
  session: AdminSession,
): Promise<BackendHealth> => {
  const response = await request(session, "/health");
  return (await response.json()) as BackendHealth;
};

export const searchDocuments = async (
  session: AdminSession,
  query: string,
  topK = 5,
): Promise<SearchResult[]> => {
  const response = await request(session, "/api/v1/documents/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
  const body = await response.json();
  return Array.isArray(body?.results) ? body.results : [];
};
