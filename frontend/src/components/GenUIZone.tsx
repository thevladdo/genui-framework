/**
 * GenUIZone Component
 * 
 * A self-contained zone that automatically renders personalized content
 * based on user profile and developer-provided prompts.
 * 
 * Usage:
 * ```tsx
 *   <GenUIZone
 *     apiUrl="http://localhost:8000"
 *     zoneId="homepage-for-you"
 *     basePrompt="Show relevant articles and resources"
 *     contextPrompt="This is the homepage. The user is looking for general information."
 *     pinnedContent={[
 *       { type: 'link', url: '/sustainability', title: 'Our Sustainability' }
 *     ]}
 *     preferredComponentType="bento"
 *     maxItems={6}
 *   />
 * ```
 */

import React, { useCallback, useEffect, useRef } from 'react';
import { ComponentRenderer } from './ComponentRenderer';
import { GenUISection } from './GenUISection';
import { useZone, UseZoneOptions, PinnedContent } from '../hooks/useZone';
import type { GenUICustomComponentDef } from '../registry';
import type { GenUITheme, GenUIComponent } from '../types';
import { getBehaviorTracker } from '../utils/behaviorTracker';
import { sendGenUIEvents } from '../utils/genuiEvents';


export interface GenUIZoneProps {
  //  Required
  /** Backend API URL */
  apiUrl: string;
  /** Unique identifier for this zone */
  zoneId: string;

  //  Auth
  /** Client API key (sent as X-API-Key). Required when the backend has CLIENT_API_KEYS configured */
  apiKey?: string;

  //  Prompt Engineering 
  /** Base prompt describing what the zone should display */
  basePrompt?: string;
  /** Developer-provided context about the zone's location and purpose */
  contextPrompt?: string;

  //  Content Control
  /** Content that must always be displayed */
  pinnedContent?: PinnedContent[];
  /**
   * Host-registered component types the LLM may generate in this zone.
   * Pair with registerGenUIComponent() so the renderer can display them.
   */
  customComponents?: GenUICustomComponentDef[];
  /** Force a specific component type (built-in or registered custom name) */
  preferredComponentType?: 'bento' | 'chart' | 'text' | 'buttons' | (string & {});
  /** Maximum number of items to display */
  maxItems?: number;

  //  User Context 
  /** User ID for profile lookup */
  userId?: string;
  /** Current page path (defaults to window.location.pathname) */
  currentPage?: string;
  /** Additional page context metadata */
  pageMetadata?: Record<string, unknown>;

  //  Behavior
  /** Whether to load automatically on mount (default: true) */
  loadOnMount?: boolean;
  /** Auto-refresh interval in milliseconds (0 = disabled) */
  refreshInterval?: number;
  /**
   * Backend cache strategy (default: 'segment').
   * 'segment' serves per-segment cached renders with stale-while-revalidate;
   * 'live' always calls the LLM — reserve it for genuinely dynamic zones.
   */
  cacheStrategy?: 'segment' | 'live';
  /**
   * Progressive render via Server-Sent Events: components appear one by
   * one as the model generates them. Most useful with cacheStrategy='live'.
   */
  streaming?: boolean;
  /**
   * Emit impression/click events to the backend for uplift measurement
   * (default: true). Impressions fire when the zone enters the viewport;
   * clicks are captured on any link inside the zone.
   */
  trackEvents?: boolean;

  //  Theming 
  /** Theme configuration */
  theme?: GenUITheme;
  /** Additional CSS class */
  className?: string;
  /** Inline styles */
  style?: React.CSSProperties;

  //  Loading/Error States 
  /** Custom loading component */
  loadingComponent?: React.ReactNode;
  /** Custom error component */
  errorComponent?: React.ReactNode | ((error: Error) => React.ReactNode);
  /** Custom empty state component */
  emptyComponent?: React.ReactNode;
  /** Show loading skeleton (default: true) */
  showLoadingSkeleton?: boolean;

  //  Callbacks 
  /** Called when zone renders successfully */
  onRender?: (components: GenUIComponent[]) => void;
  /** Called on render error */
  onError?: (error: Error) => void;

  //  Debug 
  /** Show debug information */
  debug?: boolean;
}


const LoadingSkeleton: React.FC<{ type?: string }> = ({ type }) => {
  if (type === 'bento') {
    return (
      <div className="genui-zone-skeleton genui-zone-skeleton--bento">
        {[1, 2, 3].map(i => (
          <div key={i} className="genui-zone-skeleton__card">
            <div className="genui-zone-skeleton__title" />
            <div className="genui-zone-skeleton__text" />
            <div className="genui-zone-skeleton__text genui-zone-skeleton__text--short" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="genui-zone-skeleton">
      <div className="genui-zone-skeleton__block" />
    </div>
  );
};


export const GenUIZone: React.FC<GenUIZoneProps> = ({
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
  trackEvents = true,
  theme,
  className = '',
  style,
  loadingComponent,
  errorComponent,
  emptyComponent,
  showLoadingSkeleton = true,
  onRender,
  onError,
  debug = false,
}) => {
  const zoneRef = useRef<HTMLDivElement>(null);

  const {
    components,
    isLoading,
    error,
    meta,
    pinnedContentIncluded,
    render,
    refresh,
  } = useZone({
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
    loadOnMount,
    refreshInterval,
    cacheStrategy,
    streaming,
    onRender,
    onError,
  });

  // One impression per rendered variant
  const impressionSentForRef = useRef<string | null>(null);

  const emitEvent = useCallback(
    (eventType: string, itemTitle?: string, itemUrl?: string) => {
      if (!trackEvents) return;
      sendGenUIEvents(apiUrl, apiKey, [{
        event_type: eventType,
        zone_id: zoneId,
        render_id: meta?.renderId,
        arm: meta?.experiment?.arm,
        segment: meta?.cache?.segment,
        item_title: itemTitle,
        item_url: itemUrl,
        user_id: userId && userId !== 'anonymous' ? userId : undefined,
        ts: new Date().toISOString(),
      }]);
    },
    [trackEvents, apiUrl, apiKey, zoneId, userId, meta?.renderId, meta?.experiment?.arm, meta?.cache?.segment]
  );

  // Capture clicks on any link inside the zone (uplift measurement)
  const handleZoneClick = useCallback(
    (e: React.MouseEvent) => {
      if (!trackEvents) return;
      const target = e.target as HTMLElement | null;
      const anchor = target?.closest?.('a');
      if (!anchor) return;
      emitEvent(
        'click',
        anchor.textContent?.trim().slice(0, 200) || undefined,
        anchor.getAttribute('href') || undefined,
      );
    },
    [trackEvents, emitEvent]
  );

  // Track zone visibility: behavior analytics + impression event
  useEffect(() => {
    if (!zoneRef.current) return;
    const tracker = getBehaviorTracker();

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;

          tracker?.trackInteraction(
            zoneId,
            'genui-zone',
            'scroll-into-view',
            {
              hasContent: components.length > 0,
              personalized: meta?.personalizationApplied ?? false,
            }
          );

          // Impression: once per generated variant actually seen
          const variant = meta?.renderId ?? 'unknown';
          if (
            components.length > 0 &&
            impressionSentForRef.current !== variant
          ) {
            impressionSentForRef.current = variant;
            emitEvent('impression');
          }
        });
      },
      { threshold: 0.5 }
    );

    observer.observe(zoneRef.current);

    return () => observer.disconnect();
  }, [zoneId, components.length, meta?.personalizationApplied, meta?.renderId, emitEvent]);

  // Render loading state
  if (isLoading && components.length === 0) {
    if (loadingComponent) {
      return <>{loadingComponent}</>;
    }

    if (showLoadingSkeleton) {
      return (
        <GenUISection theme={theme} className={`genui-zone genui-zone--loading ${className}`} style={style}>
          <LoadingSkeleton type={preferredComponentType} />
        </GenUISection>
      );
    }

    return null;
  }

  // Render error state
  if (error && components.length === 0) {
    if (errorComponent) {
      return (
        <GenUISection theme={theme} className={`genui-zone genui-zone--error ${className}`} style={style}>
          {typeof errorComponent === 'function' ? errorComponent(error) : errorComponent}
        </GenUISection>
      );
    }

    return (
      <GenUISection theme={theme} className={`genui-zone genui-zone--error ${className}`} style={style}>
        <div className="genui-zone-error">
          <p>Unable to load personalized content</p>
          <button onClick={refresh} className="genui-zone-error__retry">
            Try again
          </button>
        </div>
      </GenUISection>
    );
  }

  // Render empty state
  if (!isLoading && components.length === 0) {
    if (emptyComponent) {
      return <>{emptyComponent}</>;
    }
    return null;
  }

  // Render content
  return (
    <GenUISection
      theme={theme}
      className={`genui-zone ${className}`}
      style={style}
    >
      <div
        ref={zoneRef}
        className="genui-zone__content"
        data-zone-id={zoneId}
        data-personalized={meta?.personalizationApplied ? 'true' : 'false'}
        onClickCapture={handleZoneClick}
      >
        {isLoading && components.length > 0 && (
          <div className="genui-zone__refreshing">
            <span className="genui-zone__refreshing-dot" />
          </div>
        )}

        <ComponentRenderer components={components} />

        {debug && meta && (
          <details className="genui-zone__debug">
            <summary>Zone Debug: {zoneId}</summary>
            <pre>
              {JSON.stringify({
                zoneId,
                personalized: meta.personalizationApplied,
                confidence: meta.confidence,
                reasoning: meta.reasoning,
                profileFactors: meta.profileFactors,
                pinnedIncluded: pinnedContentIncluded,
                renderedAt: meta.renderedAt,
                renderId: meta.renderId,
                cache: meta.cache,
                experiment: meta.experiment,
              }, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </GenUISection>
  );
};

export default GenUIZone;
