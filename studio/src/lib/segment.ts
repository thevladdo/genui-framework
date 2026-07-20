/**
 * Segment preview pure logic.
 *
 * Mirrors backend/segmentation/segmenter.py so the page can show the
 * segment key an audience falls into before the render comes back
 * (live renders bypass the cache, so the backend does not echo one).
 * The expected keys in tests/segment.test.cjs are pinned against the
 * real Python segmenter, edge cases included.
 *
 * The mirror assumes the backend segmentation defaults (max 3
 * interests, min confidence 0.5): the profiles built here always carry
 * confidence 1.0, so only a non-default SEGMENT_MAX_INTERESTS could
 * make the shown key diverge from the served one.
 */

import type { SanitizationReport } from "genui-framework";

export type Engagement = "low" | "mid" | "high";

export interface SegmentInput {
  role?: string;
  interests?: string[];
  /** Browsing style, e.g. explorer, focused, scanner, deep_reader, casual. */
  userType?: string;
  engagement?: Engagement | "";
}

const SLUG_MAX = 24;
const MAX_INTERESTS = 3;

/** Mirror of segmenter._slugify: strip, lower, squash non [a-z0-9], cap. */
export const slugify = (value: string): string =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, SLUG_MAX);

/**
 * The segment key this audience falls into, per the backend segmenter:
 * "role=…|int=a+b|type=…|eng=…", or "anon" with no usable signals.
 */
export const segmentKey = (input: SegmentInput): string => {
  const parts: string[] = [];

  const role = slugify(input.role ?? "");
  if (role) parts.push(`role=${role}`);

  const rawInterests = (input.interests ?? []).filter((i) => i.trim() !== "");
  if (rawInterests.length) {
    const slugs = [...new Set(rawInterests.map(slugify))]
      .sort()
      .slice(0, MAX_INTERESTS);
    parts.push(`int=${slugs.join("+")}`);
  }

  const userType = slugify(input.userType ?? "");
  if (userType) parts.push(`type=${userType}`);

  if (input.engagement) parts.push(`eng=${input.engagement}`);

  return parts.length ? parts.join("|") : "anon";
};

const ENGAGEMENT_DEPTH: Record<Engagement, number> = {
  low: 10,
  mid: 50,
  high: 90,
};

export interface RenderProfile {
  user_profile: Record<string, unknown> | null;
  behavior_data: Record<string, unknown> | null;
}

/**
 * Build the user_profile/behavior_data of a ZoneRenderRequest so that
 * the backend segmenter maps them to exactly segmentKey(input).
 * Raw labels are sent as typed; the backend slugifies with the same
 * rules as segmentKey, so key and profile cannot diverge.
 */
export const buildRenderProfile = (input: SegmentInput): RenderProfile => {
  const profile: Record<string, unknown> = {};

  const role = (input.role ?? "").trim();
  if (slugify(role)) {
    profile.preferences = { role: { value: role, confidence: 1.0 } };
  }

  const interests = (input.interests ?? [])
    .map((i) => i.trim())
    .filter(Boolean);
  if (interests.length) {
    profile.interests = Object.fromEntries(
      interests.map((i) => [i, { value: true, confidence: 1.0 }]),
    );
  }

  const behavior: Record<string, unknown> = {};
  const userType = (input.userType ?? "").trim();
  if (slugify(userType)) behavior.userType = userType;
  if (input.engagement) {
    behavior.maxScrollDepth = ENGAGEMENT_DEPTH[input.engagement];
  }

  return {
    user_profile: Object.keys(profile).length ? profile : null,
    behavior_data: Object.keys(behavior).length ? behavior : null,
  };
};

export interface PreviewComponent {
  type: string;
  data: Record<string, unknown>;
  layout?: Record<string, unknown> | null;
}

export interface PreviewCacheMeta {
  status?: string;
  strategy?: string;
  segment?: string;
  age_seconds?: number;
}

export interface PreviewMeta {
  cache?: PreviewCacheMeta;
  render_id?: string;
  confidence?: number;
  reasoning?: string;
  sanitization?: Record<string, unknown>;
}

export interface PreviewRenderResponse {
  zone_id: string;
  components: PreviewComponent[];
  personalization_applied?: boolean;
  meta?: PreviewMeta;
  rendered_at?: string;
}

/** Map the backend's snake_case meta.sanitization to the library type. */
export const toSanitizationReport = (
  meta: PreviewMeta | undefined,
): SanitizationReport => {
  const s = meta?.sanitization ?? {};
  const list = (v: unknown): string[] =>
    Array.isArray(v) ? v.map((item) => String(item)) : [];
  return {
    removedUrls: list(s.removed_urls),
    droppedComponents: list(s.dropped_components),
    removedNumbers: list(s.removed_numbers),
    policyViolations: list(s.policy_violations),
  };
};

export const sanitizationCount = (report: SanitizationReport): number =>
  report.removedUrls.length +
  report.droppedComponents.length +
  report.removedNumbers.length +
  report.policyViolations.length;

/**
 * The ZoneAgent never errors out: with no working LLM engine it degrades to a pinned-only render whose reasoning carries this sentinel.
 */
export const isFallbackRender = (meta: PreviewMeta | undefined): boolean =>
  typeof meta?.reasoning === "string" &&
  meta.reasoning.startsWith("Fallback render");
