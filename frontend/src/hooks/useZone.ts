/**
 * useZone Hook
 * Manages the rendering and state of GenUI zones
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { GenUIComponent, UserProfile } from '../types';
import type { GenUICustomComponentDef } from '../registry';
import { getProfile, profileToApiFormat } from '../utils/indexeddb';
import { getBehaviorTracker } from '../utils/behaviorTracker';
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
  /** Identity of the generated variant (shared by users on the same cache entry) */
  renderId?: string;
  /** Cache info (segment, hit status, age) */
  cache?: ZoneCacheMeta;
  /** Holdout experiment info, present when a holdout is configured */
  experiment?: ZoneExperimentMeta;
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
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [meta, setMeta] = useState<ZoneRenderMeta | null>(null);
  const [pinnedContentIncluded, setPinnedContentIncluded] = useState<string[]>([]);
  
  const mountedRef = useRef(true);
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /**
   * Render the zone
   */
  const render = useCallback(async () => {
    if (!mountedRef.current) return;
    
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

      // Get behavior data
      let behaviorData: Record<string, unknown> | null = null;
      const tracker = getBehaviorTracker();
      if (tracker) {
        behaviorData = tracker.getCompactSummary();
      }

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
        current_page: currentPage || (typeof window !== 'undefined' ? window.location.pathname : undefined),
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
        });

        return renderedComponents;
      };

      const endpoint = streaming ? '/api/v1/zone/render/stream' : '/api/v1/zone/render';
      const response = await fetch(`${apiUrl}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-API-Key': apiKey } : {}),
        },
        body: JSON.stringify(requestBody),
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
          if (!mountedRef.current) return;
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
        if (!mountedRef.current) return;
        onRender?.(finalComponents ?? []);
        return;
      }

      const data = await response.json();

      if (!mountedRef.current) return;

      const renderedComponents = applyResponse(data);
      onRender?.(renderedComponents);

    } catch (err) {
      if (!mountedRef.current) return;
      
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      onError?.(error);
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [
    apiUrl,
    apiKey,
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

  // Initial load on mount
  useEffect(() => {
    mountedRef.current = true;
    
    if (loadOnMount) {
      render();
    }

    return () => {
      mountedRef.current = false;
    };
  }, [loadOnMount]); // Only run on mount, not when render changes

  // Keep the latest render callback in a ref so the auto-refresh timer
  // doesn't reset every time a parent re-render recreates the callback
  const renderRef = useRef(render);
  renderRef.current = render;

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
