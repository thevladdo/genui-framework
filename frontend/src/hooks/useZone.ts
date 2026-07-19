/**
 * useZone Hook
 * Manages the rendering and state of GenUI zones
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { GenUIComponent, SanitizationReport, UserProfile } from '../types';
import type { GenUICustomComponentDef } from '../registry';
import { getProfile, profileToApiFormat } from '../utils/indexeddb';
import { getBehaviorTracker } from '../utils/behaviorTracker';
import { redactPII } from '../utils/privacy';
import { readSSEStream } from '../utils/sse';

// ============================================
// Types
// ============================================

export interface PinnedContent {
  /** Content type: link, article, document, custom */
  type: 'link' | 'article' | 'document' | 'custom';
  /** URL for links */
  url?: string;
  /** Display title */
  title: string;
  /** Optional description */
  description?: string;
  /** ID for articles/documents */
  id?: string;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

export interface UseZoneOptions {
  /** Backend API URL */
  apiUrl: string;
  /** Client API key (sent as X-API-Key). Required when the backend has CLIENT_API_KEYS configured */
  apiKey?: string;
  /**
   * Signed user identity token (sent as X-User-Token). Required alongside
   * userId when the backend has USER_TOKEN_SECRETS configured; mint it
   * server-side with sign_user_token() and pass it to the client.
   */
  userToken?: string;
  /** Unique identifier for this zone */
  zoneId: string;
  /** Base prompt describing what the zone should display */
  basePrompt?: string;
  /** Developer-provided context about the zone's location and purpose */
  contextPrompt?: string;
  /** Content that must always be displayed */
  pinnedContent?: PinnedContent[];
  /**
   * Host-registered component types (name + JSON schema + description)
   * the LLM may generate in this zone. Pair with registerGenUIComponent()
   * so the renderer knows how to display them.
   */
  customComponents?: GenUICustomComponentDef[];
  /** Force a specific component type (built-in or registered custom name) */
  preferredComponentType?: 'bento' | 'chart' | 'text' | 'buttons' | (string & {});
  /** Maximum number of items to display */
  maxItems?: number;
  /** User ID for profile lookup */
  userId?: string;
  /** Current page path */
  currentPage?: string;
  /** Additional page context */
  pageMetadata?: Record<string, unknown>;
  /** Whether to load automatically on mount */
  loadOnMount?: boolean;
  /** Auto-refresh interval in milliseconds (0 = disabled) */
  refreshInterval?: number;
  /**
   * Cache strategy on the backend:
   * - 'segment' (default): serve per-segment cached renders (stale-while-revalidate)
   * - 'live': always call the LLM (for genuinely dynamic zones)
   */
  cacheStrategy?: 'segment' | 'live';
  /**
   * Progressive render via Server-Sent Events: components appear one by
   * one as the model generates them. Most useful with cacheStrategy='live';
   * cache hits complete in a single burst either way. (default: false)
   */
  streaming?: boolean;
  /** Callback when zone renders successfully */
  onRender?: (components: GenUIComponent[]) => void;
  /** Callback on render error */
  onError?: (error: Error) => void;
}

export interface ZoneCacheMeta {
  /** Cache outcome: 'fresh' | 'stale' | 'miss' | 'bypass' */
  status: string;
  /** Strategy used: 'segment' | 'live' */
  strategy?: string;
  /** Segment key this render was cached under */
  segment?: string;
  /** Age of the cached render in seconds */
  ageSeconds?: number;
}

export interface ZoneExperimentMeta {
  /** Experiment arm: 'personalized' | 'control' | 'none' */
  arm: string;
  /** Configured holdout share (0-100) */
  holdoutPercent?: number;
}

export interface ZoneRenderMeta {
  confidence: number;
  reasoning: string;
  profileFactors: string[];
  personalizationApplied: boolean;
  renderedAt: string;
  /**
   * Component contract version of the responding backend (undefined on
   * older backends). When it is newer than this bundle understands,
   * unknown component types are skipped silently in production.
   */
  contractVersion?: number;
  /** Identity of the generated variant (shared by users on the same cache entry) */
  renderId?: string;
  /** Cache info (segment, hit status, age) */
  cache?: ZoneCacheMeta;
  /** Holdout experiment info, present when a holdout is configured */
  experiment?: ZoneExperimentMeta;
  /** What the backend guarantee chain removed from the model's output */
  sanitization?: SanitizationReport;
}

export interface UseZoneReturn {
  /** Rendered components */
  components: GenUIComponent[];
  /** Loading state */
  isLoading: boolean;
  /** Error state */
  error: Error | null;
  /** Render metadata */
  meta: ZoneRenderMeta | null;
  /** IDs of pinned content that was included */
  pinnedContentIncluded: string[];
  /** Manually trigger a render */
  render: () => Promise<void>;
  /** Force re-render (clears existing content first) */
  refresh: () => Promise<void>;
}

// ============================================
// Hook Implementation
// ============================================

export const useZone = (options: UseZoneOptions): UseZoneReturn => {
  const {
    apiUrl,
    apiKey,
    userToken,
    zoneId,
    basePrompt = 'Show relevant content for this user',
    contextPrompt,
    pinnedContent = [],
    customComponents,
    preferredComponentType,
    maxItems = 6,
    userId = 'anonymous',
    currentPage,
    pageMetadata,
    loadOnMount = true,
    refreshInterval = 0,
    cacheStrategy,
    streaming = false,
    onRender,
    onError,
  } = options;

  const [components, setComponents] = useState<GenUIComponent[]>([]);
  // Truthful initial state: when the zone will fetch on mount, it IS
  // loading from the very first paint. Server-side rendering only sees
  // this initial state (effects never run there), so renderToString
  // emits the loading skeleton instead of empty HTML, and the client's
  // first paint matches it: no hydration mismatch, no layout shift.
  const [isLoading, setIsLoading] = useState(loadOnMount);
  const [error, setError] = useState<Error | null>(null);
  const [meta, setMeta] = useState<ZoneRenderMeta | null>(null);
  const [pinnedContentIncluded, setPinnedContentIncluded] = useState<string[]>([]);

  const mountedRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /**
   * Render the zone
   */
  const render = useCallback(async () => {
    if (!mountedRef.current) return;

    // Last issued wins: abort the previous inflight request so a stale
    // response can never overwrite the state of a newer one
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);

    try {
      // Get user profile from IndexedDB
      let userProfile: Record<string, unknown> | null = null;
      try {
        const profile = await getProfile(userId);
        if (profile) {
          userProfile = profileToApiFormat(profile);
        }
      } catch (e) {
        console.warn('Failed to load user profile for zone:', e);
      }

      // Get behavior data (already sanitized at capture time by the tracker)
      let behaviorData: Record<string, unknown> | null = null;
      const tracker = getBehaviorTracker();
      if (tracker) {
        behaviorData = tracker.getCompactSummary();
      }

      // The auto-captured page path follows the tracker's privacy level; an
      // explicit currentPage prop is the integrator's own choice and goes raw
      const privacyLevel = tracker?.getPrivacyLevel() ?? 'balanced';
      const autoPage =
        typeof window !== 'undefined' ? window.location.pathname : undefined;
      const pagePath =
        currentPage ||
        (autoPage && privacyLevel !== 'off' ? redactPII(autoPage) : autoPage);

      // Build request
      const requestBody = {
        zone_id: zoneId,
        // 'anonymous' is the local default, not an identity: sending it
        // would share one server-side profile across all anonymous users
        user_id: userId && userId !== 'anonymous' ? userId : undefined,
        base_prompt: basePrompt,
        context_prompt: contextPrompt,
        pinned_content: pinnedContent.map(p => ({
          type: p.type,
          url: p.url,
          title: p.title,
          description: p.description,
          id: p.id,
          metadata: p.metadata,
        })),
        custom_components: customComponents?.map(c => ({
          name: c.name,
          data_schema: c.dataSchema,
          description: c.description,
          example: c.example,
        })),
        preferred_component_type: preferredComponentType,
        max_items: maxItems,
        user_profile: userProfile,
        behavior_data: behaviorData,
        current_page: pagePath,
        page_metadata: pageMetadata,
        cache_strategy: cacheStrategy,
      };

      // Applies a full /render-shaped response to local state
      const applyResponse = (data: any): GenUIComponent[] => {
        const renderedComponents: GenUIComponent[] = (data.components || []).map((c: any) => ({
          type: c.type,
          data: c.data,
          layout: c.layout,
        }));

        setComponents(renderedComponents);
        setPinnedContentIncluded(data.pinned_content_included || []);
        setMeta({
          confidence: data.meta?.confidence ?? 0.5,
          reasoning: data.meta?.reasoning ?? '',
          profileFactors: data.meta?.profile_factors ?? [],
          personalizationApplied: data.personalization_applied ?? false,
          renderedAt: data.rendered_at,
          contractVersion: data.contract_version,
          renderId: data.meta?.render_id,
          cache: data.meta?.cache
            ? {
                status: data.meta.cache.status,
                strategy: data.meta.cache.strategy,
                segment: data.meta.cache.segment,
                ageSeconds: data.meta.cache.age_seconds,
              }
            : undefined,
          experiment: data.meta?.experiment
            ? {
                arm: data.meta.experiment.arm,
                holdoutPercent: data.meta.experiment.holdout_percent,
              }
            : undefined,
          sanitization: data.meta?.sanitization
            ? {
                removedUrls: data.meta.sanitization.removed_urls ?? [],
                droppedComponents: data.meta.sanitization.dropped_components ?? [],
                removedNumbers: data.meta.sanitization.removed_numbers ?? [],
                policyViolations: data.meta.sanitization.policy_violations ?? [],
              }
            : undefined,
        });

        return renderedComponents;
      };

      const endpoint = streaming ? '/api/v1/zone/render/stream' : '/api/v1/zone/render';
      const response = await fetch(`${apiUrl}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-API-Key': apiKey } : {}),
          ...(userToken ? { 'X-User-Token': userToken } : {}),
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Zone render failed: ${response.status}`);
      }

      if (streaming && response.body) {
        // Progressive render: components appear as the model emits them;
        // the final `complete` event is authoritative and replaces them
        setComponents([]);
        let finalComponents: GenUIComponent[] | null = null;
        let streamError: Error | null = null;

        await readSSEStream(response, (event, data) => {
          if (!mountedRef.current || controller.signal.aborted) return;
          if (event === 'component') {
            setComponents(prev => [...prev, {
              type: data.type,
              data: data.data,
              layout: data.layout,
            }]);
          } else if (event === 'complete') {
            finalComponents = applyResponse(data);
          } else if (event === 'error') {
            streamError = new Error(data?.detail || 'Zone stream failed');
          }
        });

        if (streamError) throw streamError;
        if (!mountedRef.current || controller.signal.aborted) return;
        onRender?.(finalComponents ?? []);
        return;
      }

      const data = await response.json();

      if (!mountedRef.current || controller.signal.aborted) return;

      const renderedComponents = applyResponse(data);
      onRender?.(renderedComponents);

    } catch (err) {
      // An aborted request was superseded (or unmounted): not an error
      if (controller.signal.aborted) return;
      if (!mountedRef.current) return;

      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      onError?.(error);
    } finally {
      // Only the winner clears the loading flag: a superseded request
      // must not, because its successor is still loading
      if (mountedRef.current && !controller.signal.aborted) {
        setIsLoading(false);
      }
    }
  }, [
    apiUrl,
    apiKey,
    userToken,
    zoneId,
    basePrompt,
    contextPrompt,
    pinnedContent,
    customComponents,
    preferredComponentType,
    maxItems,
    userId,
    currentPage,
    pageMetadata,
    cacheStrategy,
    streaming,
    onRender,
    onError,
  ]);

  /**
   * Force refresh (same as render but clears existing components first)
   */
  const refresh = useCallback(async () => {
    setComponents([]);
    setMeta(null);
    await render();
  }, [render]);

  // Keep the latest render callback in a ref so effects and the
  // auto-refresh timer don't retrigger every time a parent re-render
  // recreates the callback (inline onRender/onError props, etc.)
  const renderRef = useRef(render);
  renderRef.current = render;

  // Mount lifecycle, kept separate from the fetch trigger below so a
  // prop change never flips mountedRef; unmount aborts the inflight fetch
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  // Everything that changes WHAT this zone requests, compared BY VALUE.
  // Hosts routinely pass fresh object/array literals on every render
  // (pinnedContent={[...]}, inline pageMetadata), so depending on prop
  // identities here would refetch on every parent re-render: a fetch
  // loop. Serializing makes an equal-value re-render a no-op, while a
  // real change (zoneId, userId, prompt, ...) triggers a refetch that
  // aborts the inflight request (last issued wins). Callbacks are
  // deliberately excluded: they change behavior, not the request.
  const requestKey = JSON.stringify([
    apiUrl,
    apiKey,
    userToken,
    zoneId,
    basePrompt,
    contextPrompt,
    pinnedContent,
    customComponents,
    preferredComponentType,
    maxItems,
    userId,
    currentPage,
    pageMetadata,
    cacheStrategy,
    streaming,
  ]);

  // Fetch on mount and again whenever the request identity changes
  // (reactive props: a zone reused across SPA routes must not serve
  // the previous route's content)
  useEffect(() => {
    if (!loadOnMount) return;
    renderRef.current();
  }, [loadOnMount, requestKey]);

  // Auto-refresh interval
  useEffect(() => {
    if (refreshInterval > 0 && loadOnMount) {
      refreshTimerRef.current = setInterval(() => {
        renderRef.current();
      }, refreshInterval);

      return () => {
        if (refreshTimerRef.current) {
          clearInterval(refreshTimerRef.current);
        }
      };
    }
  }, [refreshInterval, loadOnMount]);

  return {
    components,
    isLoading,
    error,
    meta,
    pinnedContentIncluded,
    render,
    refresh,
  };
};

export default useZone;
