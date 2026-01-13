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
  stopBehaviorTracker,
} from '../utils/behaviorTracker';


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

export const useGenUI = (options: UseGenUIOptionsExtended): UseGenUIReturnExtended => {
  const {
    apiUrl,
    userId = 'anonymous',
    enablePersistence = true,
    enableBehaviorTracking = true,
    behaviorTrackingOptions,
    onProfileUpdate,
    onError,
  } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [history, setHistory] = useState<ConversationMessage[]>([]);
  const [behaviorTracker, setBehaviorTracker] = useState<BehaviorTracker | null>(null);
  
  const sessionIdRef = useRef<string>(generateSessionId());

  // Initialize profile, history, and behavior tracker on mount
  useEffect(() => {
    const init = async () => {
      // Initialize behavior tracking
      if (enableBehaviorTracking) {
        const tracker = initBehaviorTracker({
          sessionId: sessionIdRef.current,
          userId,
          ...behaviorTrackingOptions,
        });
        setBehaviorTracker(tracker);
      }

      if (!enablePersistence) return;

      try {
        // Load profile
        let loadedProfile = await getProfile(userId);
        if (!loadedProfile) {
          loadedProfile = createEmptyProfile(userId);
        }
        setProfile(loadedProfile);

        // Load conversation history
        const loadedHistory = await getConversationHistory(sessionIdRef.current);
        setHistory(loadedHistory);
      } catch (err) {
        console.error('Failed to initialize GenUI:', err);
      }
    };

    init();

    return () => {
      if (enableBehaviorTracking) {
        stopBehaviorTracker();
      }
    };
  }, [userId, enablePersistence, enableBehaviorTracking]);


  const query = useCallback(async (text: string): Promise<GenUIResponse> => {
    setIsLoading(true);
    setError(null);

    try {
      // Add user message to history
      const userMessage: ConversationMessage = {
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      };

      if (enablePersistence) {
        await addToHistory(sessionIdRef.current, userMessage);
      }
      
      setHistory(prev => [...prev, userMessage]);

      // Get behavior data
      const tracker = getBehaviorTracker();
      const behaviorData = tracker ? tracker.getCompactSummary() : null;

      // Prepare request body
      const requestBody = {
        query: text,
        user_profile: profile ? profileToApiFormat(profile) : null,
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
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }

      const data = await response.json();

      // Transform snake_case to camelCase
      const genUIResponse: GenUIResponse = {
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
        },
      };

      // Add assistant message to history
      const assistantMessage: ConversationMessage = {
        role: 'assistant',
        content: genUIResponse.text,
        timestamp: new Date().toISOString(),
      };

      if (enablePersistence) {
        await addToHistory(sessionIdRef.current, assistantMessage);
      }
      
      setHistory(prev => [...prev, assistantMessage]);

      // Handle profile updates (including behavior-derived updates)
      if (genUIResponse.profileUpdates.shouldUpdate && enablePersistence) {
        const updatedProfile = await applyProfileUpdates(
          userId,
          genUIResponse.profileUpdates.updates
        );
        setProfile(updatedProfile);
        onProfileUpdate?.(updatedProfile);
      }

      // Reset behavior tracker after successful query (data was sent)
      if (tracker) {
        tracker.reset();
      }

      return genUIResponse;

    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      onError?.(error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [apiUrl, userId, profile, history, enablePersistence, onProfileUpdate, onError]);


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
   * Clear profile data
   */
  const clearProfile = useCallback(async () => {
    if (enablePersistence) {
      await clearProfileDB(userId);
    }
    setProfile(createEmptyProfile(userId));
  }, [userId, enablePersistence]);


  /**
   * Clear conversation history
   */
  const clearConversationHistory = useCallback(async () => {
    if (enablePersistence) {
      await clearHistoryDB(sessionIdRef.current);
    }

    setHistory([]);
    sessionIdRef.current = generateSessionId();
    
    if (enableBehaviorTracking) {
      const tracker = initBehaviorTracker({
        sessionId: sessionIdRef.current,
        userId,
        ...behaviorTrackingOptions,
      });
      setBehaviorTracker(tracker);
    }
  }, [enablePersistence, enableBehaviorTracking, userId, behaviorTrackingOptions]);


  /**
   * Track a custom element interaction
   */
  const trackInteraction = useCallback((
    elementId: string,
    elementType: string,
    interactionType: 'click' | 'hover' | 'focus' | 'scroll-into-view',
    metadata?: Record<string, unknown>
  ) => {
    const tracker = getBehaviorTracker();
    if (tracker) {
      tracker.trackInteraction(elementId, elementType, interactionType, metadata);
    }
  }, []);


  /**
   * Track navigation to a new page/route
   */
  const trackNavigation = useCallback((path: string, title?: string) => {
    const tracker = getBehaviorTracker();
    if (tracker) {
      tracker.trackNavigation(path, title);
    }
  }, []);

  return {
    query,
    isLoading,
    error,
    profile,
    updateProfile,
    clearProfile,
    history: history.map(msg => ({ role: msg.role, content: msg.content })),
    clearHistory: clearConversationHistory,
    behaviorTracker,
    trackInteraction,
    trackNavigation,
  };
};

export default useGenUI;
