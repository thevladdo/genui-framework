/**
 * Content Studio + Measurement dashboard API client.
 */

import type { AdminSession } from "./session";
import type { CacheStats, EventStats, WarmupResult } from "./measure";

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

const request = async (
  session: AdminSession,
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

export const verifySession = async (session: AdminSession): Promise<void> => {
  await request(session, "/api/v1/documents/stats");
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
