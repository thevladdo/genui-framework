/**
 * GenUI Framework Utilities
 */

export {
  initDB,
  getProfile,
  saveProfile,
  createEmptyProfile,
  applyProfileUpdates,
  clearProfile,
  profileToApiFormat,
  getConversationHistory,
  addToHistory,
  clearHistory,
} from './indexeddb';

export type { ConversationMessage } from './indexeddb';

export {
  BehaviorTracker,
  initBehaviorTracker,
  getBehaviorTracker,
  stopBehaviorTracker,
} from './behaviorTracker';

export type {
  BehaviorRecord,
  BehaviorTrackerOptions,
  ClickEvent,
  ScrollEvent,
  PageVisit,
  HoverEvent,
  ElementInteraction,
} from './behaviorTracker';
