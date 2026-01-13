/**
 * IndexedDB Utilities for GenUI Profile Storage
 */

import { openDB, IDBPDatabase } from 'idb';
import type { UserProfile, ProfileUpdate } from '../types';

const DB_NAME = 'genui-profile-db';
const DB_VERSION = 1;
const STORE_NAME = 'profiles';
const HISTORY_STORE = 'conversation-history';

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface GenUIDB {
  profiles: {
    key: string;
    value: UserProfile;
  };
  'conversation-history': {
    key: string;
    value: {
      sessionId: string;
      messages: ConversationMessage[];
      updatedAt: string;
    };
  };
}

let dbPromise: Promise<IDBPDatabase<GenUIDB>> | null = null;

/**
 * Initialize the IndexedDB database
 */
export const initDB = async (): Promise<IDBPDatabase<GenUIDB>> => {
  if (!dbPromise) {
    dbPromise = openDB<GenUIDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME);
        }

        if (!db.objectStoreNames.contains(HISTORY_STORE)) {
          db.createObjectStore(HISTORY_STORE);
        }
      },
    });
  }
  return dbPromise;
};


/**
 * Get a user profile by ID
 */
export const getProfile = async (userId: string): Promise<UserProfile | null> => {
  try {
    const db = await initDB();
    const profile = await db.get(STORE_NAME, userId);
    return profile || null;
  } catch (error) {
    console.error('Failed to get profile:', error);
    return null;
  }
};


/**
 * Save or update a user profile
 */
export const saveProfile = async (profile: UserProfile): Promise<void> => {
  try {
    const db = await initDB();
    await db.put(STORE_NAME, profile, profile.userId);
  } catch (error) {
    console.error('Failed to save profile:', error);
    throw error;
  }
};


/**
 * Create an empty profile for a new user
 */
export const createEmptyProfile = (userId: string): UserProfile => {
  const now = new Date().toISOString();
  return {
    userId,
    preferences: {},
    interests: {},
    context: {},
    demographic: {},
    behavior: {},
    createdAt: now,
    updatedAt: now,
  };
};


/**
 * Apply profile updates from the backend
 */
export const applyProfileUpdates = async (
  userId: string,
  updates: ProfileUpdate[]
): Promise<UserProfile> => {
  let profile = await getProfile(userId);
  
  if (!profile) {
    profile = createEmptyProfile(userId);
  }
  
  for (const update of updates) {
    // Parse field path
    const [category, key] = update.field.split('.');
    
    if (!category || !key) {
      console.warn(`Invalid update field: ${update.field}`);
      continue;
    }
    
    // Ensure category exists
    const categoryKey = category as keyof Pick<UserProfile, 'preferences' | 'interests' | 'context' | 'demographic' | 'behavior'>;
    if (!(categoryKey in profile) || typeof profile[categoryKey] !== 'object') {
      continue;
    }
    
    const existingEntry = profile[categoryKey][key];
    
    // Only update if confidence is higher or entry doesn't exist
    if (!existingEntry || update.confidence > (existingEntry.confidence || 0)) {
      profile[categoryKey][key] = {
        value: update.value,
        confidence: update.confidence,
        updatedAt: update.timestamp,
      };
    }
  }
  
  profile.updatedAt = new Date().toISOString();
  await saveProfile(profile);
  
  return profile;
};


/**
 * Clear a user's profile
 */
export const clearProfile = async (userId: string): Promise<void> => {
  try {
    const db = await initDB();
    await db.delete(STORE_NAME, userId);
  } catch (error) {
    console.error('Failed to clear profile:', error);
    throw error;
  }
};


/**
 * Convert profile to a format suitable for the API
 */
export const profileToApiFormat = (profile: UserProfile): Record<string, unknown> => {
  const result: Record<string, unknown> = {
    userId: profile.userId,
    preferences: {},
    interests: {},
    demographic: {},
    behavior: {},
    context: {},
    history_summary: '',
    interaction_patterns: {},
  };
  
  // Include preferences with full structure
  for (const [key, entry] of Object.entries(profile.preferences)) {
    (result.preferences as Record<string, unknown>)[key] = {
      value: entry.value,
      confidence: entry.confidence,
      updatedAt: entry.updatedAt,
    };
  }
  
  // Include interests with full structure
  for (const [key, entry] of Object.entries(profile.interests)) {
    (result.interests as Record<string, unknown>)[key] = {
      value: entry.value,
      confidence: entry.confidence,
      updatedAt: entry.updatedAt,
    };
  }
  
  // Include demographic data with full structure
  for (const [key, entry] of Object.entries(profile.demographic)) {
    (result.demographic as Record<string, unknown>)[key] = {
      value: entry.value,
      confidence: entry.confidence,
      updatedAt: entry.updatedAt,
    };
  }
  
  // Include behavior data with full structure
  for (const [key, entry] of Object.entries(profile.behavior)) {
    (result.behavior as Record<string, unknown>)[key] = {
      value: entry.value,
      confidence: entry.confidence,
      updatedAt: entry.updatedAt,
    };
    
    // Also add to interaction_patterns for backward compatibility
    (result.interaction_patterns as Record<string, unknown>)[key] = entry.value;
  }
  
  // Include context with full structure
  for (const [key, entry] of Object.entries(profile.context)) {
    (result.context as Record<string, unknown>)[key] = {
      value: entry.value,
      confidence: entry.confidence,
      updatedAt: entry.updatedAt,
    };
  }
  
  // Build history summary from interests and context
  const summaryParts: string[] = [];
  
  for (const [key, entry] of Object.entries(profile.interests)) {
    summaryParts.push(`Interested in ${key}: ${entry.value}`);
  }
  
  for (const [key, entry] of Object.entries(profile.context)) {
    summaryParts.push(`${key}: ${entry.value}`);
  }
  
  result.history_summary = summaryParts.join('. ');
  
  return result;
};




// Conversation History Management

/**
 * Get conversation history for a session
 */
export const getConversationHistory = async (
  sessionId: string
): Promise<ConversationMessage[]> => {
  try {
    const db = await initDB();
    const session = await db.get(HISTORY_STORE, sessionId);
    return session?.messages || [];
  } catch (error) {
    console.error('Failed to get conversation history:', error);
    return [];
  }
};


/**
 * Add a message to conversation history
 */
export const addToHistory = async (
  sessionId: string,
  message: ConversationMessage
): Promise<void> => {
  try {
    const db = await initDB();
    const existing = await db.get(HISTORY_STORE, sessionId);
    
    const session = existing || {
      sessionId,
      messages: [],
      updatedAt: new Date().toISOString(),
    };
    
    session.messages.push(message);
    session.updatedAt = new Date().toISOString();
    
    // Keep only last 50 messages to prevent unbounded growth
    if (session.messages.length > 50) {
      session.messages = session.messages.slice(-50);
    }
    
    await db.put(HISTORY_STORE, session, sessionId);
  } catch (error) {
    console.error('Failed to add to history:', error);
  }
};


/**
 * Clear conversation history for a session
 */
export const clearHistory = async (sessionId: string): Promise<void> => {
  try {
    const db = await initDB();
    await db.delete(HISTORY_STORE, sessionId);
  } catch (error) {
    console.error('Failed to clear history:', error);
  }
};
