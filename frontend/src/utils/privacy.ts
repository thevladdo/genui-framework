/**
 * Privacy filter for behavior tracking.
 *
 * Pure module — no DOM, React or browser imports — so the capture contract
 * is testable in Node (tests/privacy.test.cjs). The BehaviorTracker routes
 * every captured string through these functions; what each privacy level
 * lets out is documented in the README ("Behavior Tracking & Privacy").
 */

export type PrivacyLevel = 'strict' | 'balanced' | 'off';

/** Marks an element (and its subtree) the tracker must not record at all */
export const PRIVATE_SELECTOR = '[data-genui-private]';
/** Marks an element (and its subtree) tracked as shape only, never content */
export const REDACT_SELECTOR = '[data-genui-redact]';

export const REDACTED_TOKEN = '[redacted]';

/** Minimal structural view of a DOM element so tests don't need a browser */
export interface ElementLike {
  closest?: (selector: string) => unknown;
  tagName?: string;
  isContentEditable?: boolean;
}

export const isPrivateElement = (el: ElementLike | null | undefined): boolean =>
  !!el?.closest?.(PRIVATE_SELECTOR);

export const isRedactedElement = (el: ElementLike | null | undefined): boolean =>
  !!el?.closest?.(REDACT_SELECTOR);

const FORM_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT', 'OPTION']);

/** Form fields: their content is never captured, at any privacy level */
export const isFormField = (el: ElementLike | null | undefined): boolean =>
  !!el && (FORM_TAGS.has((el.tagName || '').toUpperCase()) || !!el.isContentEditable);

// Common PII shapes. Deliberately conservative: over-redacting a product code
// is acceptable, leaking a card/IBAN/email is not. Free-text street addresses
// are NOT reliably detectable by regex — mark address blocks with
// data-genui-private instead (documented in the capture contract).
const PII_PATTERNS: RegExp[] = [
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, // email
  /\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b/gi, // IBAN
  /\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b/gi, // IT codice fiscale
  /\d(?:[\s./-]?\d){7,}/g, // 8+ digit runs: cards, phones, account numbers, birth dates
];

/** Replace common PII patterns in free text with REDACTED_TOKEN */
export const redactPII = (text: string): string => {
  let out = text;
  for (const pattern of PII_PATTERNS) out = out.replace(pattern, REDACTED_TOKEN);
  return out;
};

/**
 * Sanitize a captured free-text value:
 * strict → dropped (structural signals only), balanced → PII-redacted, off → raw.
 */
export const sanitizeText = (
  text: string | null | undefined,
  level: PrivacyLevel,
): string | undefined => {
  if (text == null) return undefined;
  if (level === 'strict') return undefined;
  return level === 'off' ? text : redactPII(text);
};

/**
 * Recursively sanitize a metadata value (host-provided, arbitrary shape).
 * Strings follow sanitizeText; depth is capped so cyclic objects can't hang us.
 */
export const sanitizeValue = (value: unknown, level: PrivacyLevel, depth = 0): unknown => {
  if (level === 'off' || value == null) return value;
  if (typeof value === 'string') return level === 'strict' ? undefined : redactPII(value);
  if (typeof value !== 'object') return value; // numbers, booleans
  if (depth >= 4) return undefined;
  if (Array.isArray(value)) return value.map((v) => sanitizeValue(v, level, depth + 1));
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    out[k] = sanitizeValue(v, level, depth + 1);
  }
  return out;
};

/**
 * The single gate for everything that needs the visitor's agreement:
 * behavior capture, the profile in IndexedDB, and sending a persistent
 * identifier with a request.
 *
 * Only an explicit `true` opens it. Storing or reading information on
 * someone's terminal equipment takes consent given, never consent
 * assumed, so an integrator who has not wired a consent flow yet gets
 * the anonymous mode rather than a quiet write to the visitor's
 * browser. The library still personalizes in that mode: it is served
 * the archetype of an anonymous segment.
 *
 * Consent given here also settles the ambient browser signals: a
 * visitor who answered a consent prompt has made a more specific
 * statement than a browser-wide default, and nothing runs without that
 * answer anyway.
 */
export const consentGranted = (consent?: boolean): boolean => consent === true;
