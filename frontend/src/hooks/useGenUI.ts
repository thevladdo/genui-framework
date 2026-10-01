/**
 * useGenUI Hook
 * Main hook for interacting with the GenUI backend
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import type { 
  UseGenUIOptions, 
  UseGenUIReturn, 
  GenUIResponse, 
  UserProfile 
} from '../types';
import {
  getProfile,
  createEmptyProfile,
  profileScope,
  applyProfileUpdates,
  clearProfile as clearProfileDB,
  profileToApiFormat,
  getConversationHistory,
  addToHistory,
  clearHistory as clearHistoryDB,
  ConversationMessage,
} from '../utils/indexeddb';
import {
  BehaviorTracker,
  BehaviorTrackerOptions,
  initBehaviorTracker,
  getBehaviorTracker,
  behaviorTrackerFor,
  stopBehaviorTracker,
} from '../utils/behaviorTracker';
import {
  DEFAULT_CHAT_DISCLOSURE_TEXT,
  parseDisclosure,
  type GenUIDisclosure,
} from '../utils/disclosure';
import { consentGranted } from '../utils/privacy';
import { GenUIError, asGenUIError, errorFromResponse } from '../utils/errors';


const generateSessionId = (): string => {
  return `session_${Date.now()}_${Math.random().toString(36).substring(7)}`;
};

export interface UseGenUIOptionsExtended extends UseGenUIOptions {
  enableBehaviorTracking?: boolean;
  behaviorTrackingOptions?: Partial<BehaviorTrackerOptions>;
}

export interface UseGenUIReturnExtended extends UseGenUIReturn {
  behaviorTracker: BehaviorTracker | null;
  trackInteraction: (elementId: string, elementType: string, interactionType: 'click' | 'hover' | 'focus' | 'scroll-into-view', metadata?: Record<string, unknown>) => void;
  trackNavigation: (path: string, title?: string) => void;
}

/**
 * What a chat UI needs to tell the person who it is talking to.
 *
 * `notice` exists before anything has been sent, because that
 * information is due at the latest at the first interaction: the host
 * renders it next to the input, not after the first answer comes back.
 * `lastResponse` is the marking of the answer just received, for hosts
 * that also label each message.
 */
export interface GenUIChatDisclosure {
  /** True whenever answers come from a model, which for this hook is always */
  aiInteraction: boolean;
  /** Ready-to-render wording; override it with the `disclosureText` option */
  notice: string;
  /** Marking of the last answer, null before the first exchange */
  lastResponse: GenUIDisclosure | null;
}

export const useGenUI = (options: UseGenUIOptionsExtended): UseGenUIReturnExtended => {
  const {
    apiUrl,
    apiKey,
    userToken,
    userId = 'anonymous',
    enablePersistence = true,
    enableBehaviorTracking = true,
    behaviorTrackingOptions,
    privacy,
    consent,
    disclosureText,
    onProfileUpdate,
    onError,
  } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<GenUIError | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [history, setHistory] = useState<ConversationMessage[]>([]);
  const [behaviorTracker, setBehaviorTracker] = useState<BehaviorTracker | null>(null);
  const [lastDisclosure, setLastDisclosure] = useState<GenUIDisclosure | null>(null);

  // The profile and the conversation history live in IndexedDB, on the
  // visitor's own device, so persistence needs their agreement on top of
  // the integrator's. Denied, the chat still answers: it just answers
  // without remembering anything locally and without naming anyone.
  const persist = enablePersistence && consentGranted(consent);
  const storeScope = profileScope(apiUrl, apiKey);

  const sessionIdRef = useRef<string>(generateSessionId());

  // Everything this hook holds in memory belongs to one identity: the backend, the key, the user and their consent.
  // When any of them changes, the session, history and profile of the previous one are dropped, and the answers still in flight for it are aborted and discarded, so nothing of it can reach the next request.
  const identity = JSON.stringify([apiUrl, apiKey ?? null, userId, consentGranted(consent)]);
  const identityRef = useRef(identity);
  const identityScopeRef = useRef(new AbortController());

  useEffect(() => {
    if (identityRef.current === identity) return;
    identityRef.current = identity;
    identityScopeRef.current.abort();
    identityScopeRef.current = new AbortController();
    sessionIdRef.current = generateSessionId();
    setHistory([]);
    setProfile(null);
    setError(null);
    setLastDisclosure(null);
    setIsLoading(false);
  }, [identity]);

  // Initialize profile, history, and behavior tracker for the current identity
  useEffect(() => {
    // Without consent no tracker is created at all, rather than one that
    // exists and never captures: a dormant instance would also shadow the
    // one a zone on the same page is entitled to start.
    const tracker =
      enableBehaviorTracking && consentGranted(consent)
        ? initBehaviorTracker({
            sessionId: sessionIdRef.current,
            userId,
            privacy,
            consent,
            ...behaviorTrackingOptions,
          })
        : null;
    setBehaviorTracker(tracker);

    let cancelled = false;
    const init = async () => {
      if (!persist) return;

      try {
        const loadedProfile =
          (await getProfile(userId, storeScope)) ?? createEmptyProfile(userId);
        const loadedHistory = await getConversationHistory(sessionIdRef.current);
        if (cancelled) return;
        setProfile(loadedProfile);
        setHistory(loadedHistory);
      } catch (err) {
        console.error('Failed to initialize GenUI:', err);
      }
    };

    init();

    // Only stop what this hook started: on a page that also has zones,
    // the running tracker may not be ours to shut down.
    return () => {
      cancelled = true;
      if (tracker && getBehaviorTracker() === tracker) {
        stopBehaviorTracker();
      }
    };
  }, [userId, storeScope, persist, enableBehaviorTracking, privacy, consent]);


  const query = useCallback(async (text: string): Promise<GenUIResponse> => {
    const scope = identityScopeRef.current.signal;
    const sessionId = sessionIdRef.current;
    const consented = consentGranted(consent);
    // After every await: an answer for an identity that is gone lands nowhere
    const ensureCurrent = () => {
      if (scope.aborted) throw new DOMException('Identity changed', 'AbortError');
    };

    setIsLoading(true);
    setError(null);

    try {
      // Add user message to history
      const userMessage: ConversationMessage = {
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      };

      if (persist) {
        await addToHistory(sessionId, userMessage);
        ensureCurrent();
      }
      
      setHistory(prev => [...prev, userMessage]);

      const tracker = behaviorTrackerFor(userId, consent);
      const behaviorData = tracker ? tracker.getCompactSummary() : null;

      // Prepare request body
      const requestBody = {
        query: text,
        // 'anonymous' is the local default, not an identity: sending it
        // would share one server-side profile across all anonymous users
        user_id: consented && userId && userId !== 'anonymous' ? userId : undefined,
        user_profile: consented && profile ? profileToApiFormat(profile) : null,
        conversation_history: history.slice(-10).map(msg => ({
          role: msg.role,
          content: msg.content,
        })),
        behavior_data: behaviorData,
      };


      const response = await fetch(`${apiUrl}/api/v1/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-API-Key': apiKey } : {}),
          ...(userToken ? { 'X-User-Token': userToken } : {}),
        },
        body: JSON.stringify(requestBody),
        signal: scope,
      });

      if (!response.ok) {
        const error = await errorFromResponse(response, 'API error');
        ensureCurrent();
        throw error;
      }

      const data = await response.json();
      ensureCurrent();

      // Transform snake_case to camelCase
      const genUIResponse: GenUIResponse = {
        contractVersion: data.contract_version,
        text: data.text,
        components: data.components,
        sources: data.sources,
        suggestedActions: data.suggested_actions,
        profileUpdates: {
          shouldUpdate: data.profile_updates?.should_update ?? false,
          updates: data.profile_updates?.updates ?? [],
        },
        meta: {
          confidence: data.meta?.confidence ?? 0.5,
          interactionType: data.meta?.interaction_type ?? 'question',
          topics: data.meta?.topics ?? [],
          sentiment: data.meta?.sentiment ?? 'neutral',
          behavior: data.meta?.behavior
            ? {
                engagementScore: data.meta.behavior.engagement_score ?? 0,
                userType: data.meta.behavior.user_type ?? 'casual',
                sessionSummary: data.meta.behavior.session_summary ?? '',
                insightsCount: data.meta.behavior.insights_count ?? 0,
                uiAdjustments: data.meta.behavior.ui_adjustments ?? [],
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
          disclosure: parseDisclosure(data.meta?.disclosure),
        },
      };

      setLastDisclosure(genUIResponse.meta.disclosure ?? null);

      // Add assistant message to history
      const assistantMessage: ConversationMessage = {
        role: 'assistant',
        content: genUIResponse.text,
        timestamp: new Date().toISOString(),
      };

      if (persist) {
        await addToHistory(sessionId, assistantMessage);
        ensureCurrent();
      }
      
      setHistory(prev => [...prev, assistantMessage]);

      // Handle profile updates (including behavior-derived updates)
      if (genUIResponse.profileUpdates.shouldUpdate && persist) {
        const updatedProfile = await applyProfileUpdates(
          userId,
          genUIResponse.profileUpdates.updates,
          storeScope
        );
        ensureCurrent();
        setProfile(updatedProfile);
        onProfileUpdate?.(updatedProfile);
      }

      // Reset behavior tracker after successful query (data was sent)
      if (tracker) {
        tracker.reset();
      }

      return genUIResponse;

    } catch (err) {
      // Discarded with its identity: not an error of the current one
      if (scope.aborted) throw err;
      const error = asGenUIError(err);
      setError(error);
      onError?.(error);
      throw error;
    } finally {
      if (!scope.aborted) setIsLoading(false);
    }
  }, [apiUrl, apiKey, userToken, userId, consent, profile, history, persist, storeScope, onProfileUpdate, onError]);


  /**
   * Manually update profile
   */
  const updateProfile = useCallback((updates: Partial<UserProfile>) => {
    setProfile(prev => {
      if (!prev) return null;
      const updated = { ...prev, ...updates, updatedAt: new Date().toISOString() };
      return updated;
    });
  }, []);


  /**
   * Clear profile data.
   * Erasing local data is never gated on consent: withdrawing it is
   * exactly when someone wants their device cleaned.
   */
  const clearProfile = useCallback(async () => {
    if (enablePersistence) {
      await clearProfileDB(userId, storeScope);
    }
    setProfile(createEmptyProfile(userId));
  }, [userId, storeScope, enablePersistence]);


  /**
   * Clear conversation history
   */
  const clearConversationHistory = useCallback(async () => {
    if (enablePersistence) {
      await clearHistoryDB(sessionIdRef.current);
    }

    setHistory([]);
    sessionIdRef.current = generateSessionId();

    if (enableBehaviorTracking && consentGranted(consent)) {
      const tracker = initBehaviorTracker({
        sessionId: sessionIdRef.current,
        userId,
        privacy,
        consent,
        ...behaviorTrackingOptions,
      });
      setBehaviorTracker(tracker);
    }
  }, [enablePersistence, enableBehaviorTracking, userId, behaviorTrackingOptions, privacy, consent]);


  /**
   * Track a custom element interaction
   */
  const trackInteraction = useCallback((
    elementId: string,
    elementType: string,
    interactionType: 'click' | 'hover' | 'focus' | 'scroll-into-view',
    metadata?: Record<string, unknown>
  ) => {
    behaviorTrackerFor(userId, consent)?.trackInteraction(elementId, elementType, interactionType, metadata);
  }, [userId, consent]);


  /**
   * Track navigation to a new page/route
   */
  const trackNavigation = useCallback((path: string, title?: string) => {
    behaviorTrackerFor(userId, consent)?.trackNavigation(path, title);
  }, [userId, consent]);

  return {
    query,
    isLoading,
    error,
    profile,
    updateProfile,
    clearProfile,
    history: history.map(msg => ({ role: msg.role, content: msg.content })),
    clearHistory: clearConversationHistory,
    disclosure: {
      aiInteraction: true,
      notice: disclosureText ?? DEFAULT_CHAT_DISCLOSURE_TEXT,
      lastResponse: lastDisclosure,
    },
    behaviorTracker,
    trackInteraction,
    trackNavigation,
  };
};

export default useGenUI;
