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

export { sanitizeUrl } from './sanitizeUrl';

export { sendGenUIEvents } from './genuiEvents';
export type { GenUIEvent } from './genuiEvents';

export {
  DEFAULT_CHAT_DISCLOSURE_TEXT,
  DEFAULT_DISCLOSURE_TEXT,
  digitalSourceType,
  disclosureJsonLd,
  noticeComesFirst,
  parseDisclosure,
} from './disclosure';

export type {
  GenUIDisclosure,
  GenUIDisclosureOptions,
  GenUIDisclosurePosition,
  GenUIProvenance,
} from './disclosure';
