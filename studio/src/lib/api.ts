/**
 * Content Studio + Measurement dashboard API client.
 */

import { isActive, type AdminSession } from "./session";
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
  contextualized?: boolean;
}

export interface CorpusState {
  tokens: number;
  threshold_tokens: number;
  contextual_indexing: boolean;
  chunks_total: number;
  chunks_contextualized: number;
  chunks_plain: number;
  budget_per_hour: number | null;
  max_upload_bytes?: number;
}

/** A file the backend would refuse with 413; without a reported limit the backend decides. */
export const tooLarge = (
  size: number,
  corpus: Pick<CorpusState, "max_upload_bytes"> | null,
): boolean =>
  corpus?.max_upload_bytes !== undefined && size > corpus.max_upload_bytes;

export const uploadLimitLabel = (bytes: number): string =>
  `${Math.floor(bytes / (1024 * 1024))} MB`;

export interface KnowledgeBase {
  documents: KnowledgeDocument[];
  corpus: CorpusState | null;
}

export interface IndexReport {
  status: "completed" | "partial" | "cancelled" | "estimated" | string;
  chunks_created: number;
  chunks_indexed: number;
  chunks_failed?: number;
  chunks_payload_updated?: number;
  error?: string;
  contextual_indexing: boolean;
  context_calls: number;
  prompt_cache: string | null;
  threshold_tokens: number;
  crosses_threshold: boolean;
  chunks_left_behind?: number;
  budget_exceeded?: boolean;
  cancelled?: boolean;
  source?: string;
}

export interface IngestStatus {
  phase:
    | "contextualizing"
    | "indexing"
    | "done"
    | "cancelled"
    | "failed"
    | "unknown"
    | string;
  source?: string;
  total: number;
  done: number;
  cancelled?: boolean;
  started_at?: number;
}

export interface BackfillReport {
  status: "completed" | "partial" | "cancelled" | "estimated" | string;
  chunks_plain: number;
  context_calls: number;
  chunks_contextualized: number;
  chunks_plain_remaining?: number;
  prompt_cache?: string | null;
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
    let requestId: string | null = null;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
      if (typeof body?.request_id === "string") requestId = body.request_id;
    } catch {
      // Non-JSON error body
    }
    requestId ??= response.status >= 500 ? response.headers?.get?.("X-Request-ID") ?? null : null;
    throw Object.assign(new Error(requestId ? `${detail} (request id ${requestId})` : detail), { status: response.status });
  }

  return response;
};

const never = <T>(): Promise<T> => new Promise<T>(() => {});

// Scoped to one tenant session, checked when the call leaves and again when the body has arrived.
const request = async <T = unknown>(
  session: AdminSession,
  path: string,
  init: RequestInit = {},
): Promise<T> => {
  if (!isActive(session)) {
    throw new Error(
      `This view is scoped to tenant "${session.tenant}", which is no longer ` +
        "the active session. Reload the page to work on the current tenant.",
    );
  }
  let body: T;
  try {
    body = (await (await call(session, path, init)).json()) as T;
  } catch (error) {
    if (!isActive(session)) return never<T>();
    throw error;
  }
  return isActive(session) ? body : never<T>();
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
): Promise<KnowledgeBase> => {
  const body = await request<Partial<KnowledgeBase> | null>(
    session,
    "/api/v1/documents",
  );
  return {
    documents: Array.isArray(body?.documents) ? body.documents : [],
    corpus: body?.corpus ?? null,
  };
};

export const uploadDocument = async (
  session: AdminSession,
  file: File,
  options: { dryRun?: boolean; ingestId?: string } = {},
): Promise<IndexReport> => {
  const form = new FormData();
  form.append("file", file);
  if (options.dryRun) form.append("dry_run", "true");
  if (options.ingestId) form.append("ingest_id", options.ingestId);
  return request<IndexReport>(session, "/api/v1/documents/upload", {
    method: "POST",
    body: form,
  });
};

export const readIngest = async (
  session: AdminSession,
  ingestId: string,
): Promise<IngestStatus> => {
  return request<IngestStatus>(
    session,
    `/api/v1/documents/ingest/${encodeURIComponent(ingestId)}`,
  );
};

export const cancelIngest = async (
  session: AdminSession,
  ingestId: string,
): Promise<void> => {
  await request(
    session,
    `/api/v1/documents/ingest/${encodeURIComponent(ingestId)}/cancel`,
    { method: "POST" },
  );
};

export const backfillContext = async (
  session: AdminSession,
  options: { dryRun?: boolean; maxChunks?: number; ingestId?: string } = {},
): Promise<BackfillReport> => {
  return request<BackfillReport>(session, "/api/v1/documents/backfill", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dry_run: options.dryRun ?? false,
      ...(options.maxChunks ? { max_chunks: options.maxChunks } : {}),
      ...(options.ingestId ? { ingest_id: options.ingestId } : {}),
    }),
  });
};

/**
 * A backfill walked in runs under one id, each run picking up where the last
 * stopped. Only `partial` carries on: `cancelled` is the operator's stop,
 * and carrying on after it is a new run with a new id.
 */
export const backfillInRuns = async (
  session: AdminSession,
  ingestId: string,
  onRemaining: (remaining: number) => void,
): Promise<BackfillReport> => {
  for (;;) {
    const report = await backfillContext(session, { ingestId });
    const remaining = report.chunks_plain_remaining ?? 0;
    onRemaining(remaining);
    if (
      report.status !== "partial" ||
      report.chunks_contextualized === 0 ||
      remaining === 0
    ) {
      return report;
    }
  }
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
  return request<EventStats>(
    session,
    `/api/v1/events/stats?zone_id=${encodeURIComponent(zoneId)}`,
  );
};

export const zoneCacheStats = async (
  session: AdminSession,
): Promise<CacheStats> => {
  return request<CacheStats>(session, "/api/v1/zone/cache/stats");
};

export const warmupZones = async (
  session: AdminSession,
  zones: unknown[],
): Promise<WarmupResult> => {
  return request<WarmupResult>(session, "/api/v1/zone/warmup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zones }),
  });
};

export const renderZone = async (
  session: AdminSession,
  payload: Record<string, unknown>,
): Promise<PreviewRenderResponse> => {
  return request<PreviewRenderResponse>(session, "/api/v1/zone/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
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
  return request<ZoneListResponse>(session, CONFIG_BASE);
};

export const getZoneConfig = async (
  session: AdminSession,
  zoneId: string,
): Promise<ZoneConfigDetail> => {
  return request<ZoneConfigDetail>(
    session,
    `${CONFIG_BASE}/${encodeURIComponent(zoneId)}`,
  );
};

export const saveZoneDraft = async (
  session: AdminSession,
  zoneId: string,
  config: Record<string, unknown>,
  expectedVersion?: number | null,
): Promise<ZoneWriteResponse> => {
  return request<ZoneWriteResponse>(
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
};

export const approveZoneConfig = async (
  session: AdminSession,
  zoneId: string,
  expectedVersion?: number | null,
): Promise<ZoneWriteResponse> => {
  return request<ZoneWriteResponse>(
    session,
    `${CONFIG_BASE}/${encodeURIComponent(zoneId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion ?? null }),
    },
  );
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
  expectedVersion?: number | null,
): Promise<void> => {
  const query =
    expectedVersion == null ? "" : `?expected_version=${expectedVersion}`;
  await request(
    session,
    `${CONFIG_BASE}/${encodeURIComponent(zoneId)}${query}`,
    {
      method: "DELETE",
    },
  );
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
  return request<AuditQueryResponse>(session, `/api/v1/audit${suffix}`);
};

export interface ContentPolicyResponse {
  banned_terms: string[];
  env_terms: string[];
  storage: string;
}

export const getContentPolicy = async (
  session: AdminSession,
): Promise<ContentPolicyResponse> => {
  return request<ContentPolicyResponse>(session, "/api/v1/content-policy");
};

export const saveContentPolicy = async (
  session: AdminSession,
  bannedTerms: string[],
): Promise<ContentPolicyResponse> => {
  return request<ContentPolicyResponse>(session, "/api/v1/content-policy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ banned_terms: bannedTerms }),
  });
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
  return request<TenantThemeResponse>(session, "/api/v1/theme");
};

export const saveTenantTheme = async (
  session: AdminSession,
  theme: Record<string, string>,
): Promise<TenantThemeWriteResponse> => {
  return request<TenantThemeWriteResponse>(session, "/api/v1/theme", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme }),
  });
};

export interface BackendHealth {
  status?: string;
  llm?: string;
  redis?: string;
}

export const backendHealth = async (
  session: AdminSession,
): Promise<BackendHealth> => {
  return request<BackendHealth>(session, "/health");
};

export const searchDocuments = async (
  session: AdminSession,
  query: string,
  topK = 5,
): Promise<SearchResult[]> => {
  const body = await request<{ results?: SearchResult[] } | null>(
    session,
    "/api/v1/documents/search",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK }),
    },
  );
  return Array.isArray(body?.results) ? body.results : [];
};
