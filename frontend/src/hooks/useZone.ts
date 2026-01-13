/**
 * useZone Hook
 * Manages the rendering and state of GenUI zones
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { GenUIComponent, UserProfile } from '../types';
import { getProfile, profileToApiFormat } from '../utils/indexeddb';
import { getBehaviorTracker } from '../utils/behaviorTracker';

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
  /** Unique identifier for this zone */
  zoneId: string;
  /** Base prompt describing what the zone should display */
  basePrompt?: string;
  /** Developer-provided context about the zone's location and purpose */
  contextPrompt?: string;
  /** Content that must always be displayed */
  pinnedContent?: PinnedContent[];
  /** Force a specific component type */
  preferredComponentType?: 'bento' | 'chart' | 'text' | 'buttons';
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
  /** Callback when zone renders successfully */
  onRender?: (components: GenUIComponent[]) => void;
  /** Callback on render error */
  onError?: (error: Error) => void;
}

export interface ZoneRenderMeta {
  confidence: number;
  reasoning: string;
  profileFactors: string[];
  personalizationApplied: boolean;
  renderedAt: string;
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
    zoneId,
    basePrompt = 'Show relevant content for this user',
    contextPrompt,
    pinnedContent = [],
    preferredComponentType,
    maxItems = 6,
    userId = 'anonymous',
    currentPage,
    pageMetadata,
    loadOnMount = true,
    refreshInterval = 0,
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
        preferred_component_type: preferredComponentType,
        max_items: maxItems,
        user_profile: userProfile,
        behavior_data: behaviorData,
        current_page: currentPage || (typeof window !== 'undefined' ? window.location.pathname : undefined),
        page_metadata: pageMetadata,
      };

      // Make API request
      const response = await fetch(`${apiUrl}/api/v1/zone/render`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Zone render failed: ${response.status}`);
      }

      const data = await response.json();

      if (!mountedRef.current) return;

      // Transform response
      const renderedComponents: GenUIComponent[] = data.components.map((c: any) => ({
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
      });

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
    zoneId,
    basePrompt,
    contextPrompt,
    pinnedContent,
    preferredComponentType,
    maxItems,
    userId,
    currentPage,
    pageMetadata,
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

  // Auto-refresh interval
  useEffect(() => {
    if (refreshInterval > 0 && loadOnMount) {
      refreshTimerRef.current = setInterval(() => {
        render();
      }, refreshInterval);

      return () => {
        if (refreshTimerRef.current) {
          clearInterval(refreshTimerRef.current);
        }
      };
    }
  }, [refreshInterval, loadOnMount, render]);

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
