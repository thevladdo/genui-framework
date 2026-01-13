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

import React, { useEffect, useRef } from 'react';
import { ComponentRenderer } from './ComponentRenderer';
import { GenUISection } from './GenUISection';
import { useZone, UseZoneOptions, PinnedContent } from '../hooks/useZone';
import type { GenUITheme, GenUIComponent } from '../types';
import { getBehaviorTracker } from '../utils/behaviorTracker';


export interface GenUIZoneProps {
  //  Required 
  /** Backend API URL */
  apiUrl: string;
  /** Unique identifier for this zone */
  zoneId: string;

  //  Prompt Engineering 
  /** Base prompt describing what the zone should display */
  basePrompt?: string;
  /** Developer-provided context about the zone's location and purpose */
  contextPrompt?: string;

  //  Content Control 
  /** Content that must always be displayed */
  pinnedContent?: PinnedContent[];
  /** Force a specific component type */
  preferredComponentType?: 'bento' | 'chart' | 'text' | 'buttons';
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
    zoneId,
    basePrompt,
    contextPrompt,
    pinnedContent,
    preferredComponentType,
    maxItems,
    userId,
    currentPage,
    pageMetadata,
    loadOnMount,
    refreshInterval,
    onRender,
    onError,
  });

  // Track zone visibility for behavior analytics
  useEffect(() => {
    const tracker = getBehaviorTracker();
    if (!tracker || !zoneRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            tracker.trackInteraction(
              zoneId,
              'genui-zone',
              'scroll-into-view',
              {
                hasContent: components.length > 0,
                personalized: meta?.personalizationApplied ?? false,
              }
            );
          }
        });
      },
      { threshold: 0.5 }
    );

    observer.observe(zoneRef.current);

    return () => observer.disconnect();
  }, [zoneId, components.length, meta?.personalizationApplied]);

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
              }, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </GenUISection>
  );
};

export default GenUIZone;
