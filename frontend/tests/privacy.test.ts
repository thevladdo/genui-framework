/**
 * Privacy filter contract tests (pure, no React, no real DOM).
 * Migrated from the node:test harness to vitest (WP-09): same contract,
 * same asserts; imports the TS sources directly (no tsc pre-build step).
 *
 * The contract under test (roadmap/fondamenta/06-privacy-filter-behavior.md):
 *  - data-genui-private subtrees are never captured at all
 *  - data-genui-redact subtrees: shape only, never content
 *  - form field content is NEVER captured, at any level (even 'off')
 *  - 'balanced' (default) redacts PII patterns from captured text
 *  - 'strict' lets no free text out (no click text, no hrefs, no titles)
 *  - consent === false blocks tracking; DNT/GPC blocks unless 'off' or explicit consent
 */

import { test } from 'vitest';
import assert from 'node:assert/strict';

// Minimal window/document stubs so the tracker works outside a browser.
// Both modules are SSR-safe (no window access at import time), so the
// hoisted imports below evaluate fine before these run.
(globalThis as any).window = {
  innerWidth: 1200,
  innerHeight: 800,
  location: { pathname: '/home' },
  addEventListener() {},
  removeEventListener() {},
};
(globalThis as any).document = {
  title: 'Home',
  referrer: 'https://google.com/?q=mario+rossi+preventivo',
  hidden: false,
  addEventListener() {},
  removeEventListener() {},
};

import {
  redactPII,
  isPrivateElement,
  isRedactedElement,
  isFormField,
  trackingAllowed,
  sanitizeText,
  sanitizeValue,
} from '../src/utils/privacy';
import { BehaviorTracker } from '../src/utils/behaviorTracker';

// --- helpers ---------------------------------------------------------------

const PRIVATE_SEL = '[data-genui-private]';
const REDACT_SEL = '[data-genui-redact]';

/** Fake DOM element: `closest` answers only for the given selector */
const el = (overrides: Record<string, unknown> = {}, matches: string | null = null): any => ({
  tagName: 'DIV',
  id: 'promo-card',
  className: 'card',
  dataset: {},
  textContent: 'plain text',
  closest: (sel: string) => (sel === matches ? {} : null),
  ...overrides,
});

const clickEvent = (target: any): any => ({ clientX: 100, clientY: 100, target });

// `any`: several tests exercise TS-private members (handleClick, record)
// on purpose, exactly like the compiled-JS harness did
const newTracker = (opts: Record<string, unknown> = {}): any =>
  new BehaviorTracker({ sessionId: 's1', userId: 'u1', ...opts } as any);

// --- redactPII --------------------------------------------------------------

test('redactPII: emails, long numbers, IBAN, codice fiscale', () => {
  assert.equal(redactPII('write to mario.rossi@example.com now'), 'write to [redacted] now');
  assert.equal(redactPII('card 4111 1111 1111 1111 ok'), 'card [redacted] ok');
  assert.equal(redactPII('IBAN IT60X0542811101000000123456'), 'IBAN [redacted]');
  assert.equal(redactPII('IBAN IT60 X054 2811 1010 0000 0123 456'), 'IBAN [redacted]');
  assert.equal(redactPII('cf RSSMRA85T10A562S'), 'cf [redacted]');
  assert.equal(redactPII('call +39 333 123 4567'), 'call +[redacted]');
  assert.equal(redactPII('born 12/06/1985'), 'born [redacted]');
});

test('redactPII: harmless text and short numbers survive', () => {
  assert.equal(redactPII('Only 4 items left at €1.299'), 'Only 4 items left at €1.299');
  assert.equal(redactPII('Chapter 12, page 340'), 'Chapter 12, page 340');
  assert.equal(redactPII('Save 20% today'), 'Save 20% today');
});

// --- element predicates ------------------------------------------------------

test('isPrivateElement / isRedactedElement walk up via closest', () => {
  assert.equal(isPrivateElement(el({}, PRIVATE_SEL)), true);
  assert.equal(isPrivateElement(el()), false);
  assert.equal(isPrivateElement(null), false);
  assert.equal(isRedactedElement(el({}, REDACT_SEL)), true);
  assert.equal(isRedactedElement(el()), false);
});

test('isFormField: input, textarea, select, contenteditable', () => {
  assert.equal(isFormField(el({ tagName: 'INPUT' })), true);
  assert.equal(isFormField(el({ tagName: 'textarea' })), true);
  assert.equal(isFormField(el({ tagName: 'SELECT' })), true);
  assert.equal(isFormField(el({ tagName: 'OPTION' })), true);
  assert.equal(isFormField(el({ isContentEditable: true })), true);
  assert.equal(isFormField(el()), false);
});

// --- consent / DNT gate ------------------------------------------------------

test('trackingAllowed: consent and DNT/GPC matrix', () => {
  assert.equal(trackingAllowed({ privacy: 'balanced' } as any, {} as any), true);
  // explicit denial blocks everything, even 'off'
  assert.equal(trackingAllowed({ privacy: 'balanced', consent: false } as any, {} as any), false);
  assert.equal(trackingAllowed({ privacy: 'off', consent: false } as any, {} as any), false);
  // ambient signals block unless 'off'
  assert.equal(trackingAllowed({ privacy: 'balanced' } as any, { doNotTrack: '1' } as any), false);
  assert.equal(trackingAllowed({ privacy: 'strict' } as any, { globalPrivacyControl: true } as any), false);
  assert.equal(trackingAllowed({ privacy: 'off' } as any, { doNotTrack: '1' } as any), true);
  // explicit consent (host CMP) overrides the ambient browser signal
  assert.equal(trackingAllowed({ privacy: 'balanced', consent: true } as any, { doNotTrack: '1' } as any), true);
});

test('tracker.start() is a no-op without consent', () => {
  const denied = newTracker({ consent: false });
  denied.start();
  assert.equal(denied.isTracking, false);

  const granted = newTracker({ consent: true });
  granted.start();
  assert.equal(granted.isTracking, true);
  granted.stop();
});

// --- sanitize helpers --------------------------------------------------------

test('sanitizeText per level', () => {
  assert.equal(sanitizeText('mail a@b.com', 'strict'), undefined);
  assert.equal(sanitizeText('mail a@b.com', 'balanced'), 'mail [redacted]');
  assert.equal(sanitizeText('mail a@b.com', 'off'), 'mail a@b.com');
  assert.equal(sanitizeText(undefined, 'balanced'), undefined);
});

test('sanitizeValue: deep metadata, strict drops strings, non-strings kept', () => {
  const meta = { note: 'call 333 123 4567', nested: { mail: 'a@b.com' }, count: 3, ok: true };
  const balanced = sanitizeValue(meta, 'balanced') as any;
  assert.equal(balanced.note, 'call [redacted]');
  assert.equal(balanced.nested.mail, '[redacted]');
  assert.equal(balanced.count, 3);
  assert.equal(balanced.ok, true);
  const strict = sanitizeValue(meta, 'strict') as any;
  assert.equal(strict.note, undefined);
  assert.equal(strict.nested.mail, undefined);
  assert.equal(strict.count, 3);
});

// --- tracker capture contract ------------------------------------------------

test('data-genui-private: the click is not captured at all', () => {
  const t = newTracker();
  t.handleClick(clickEvent(el({ textContent: 'secret quote' }, PRIVATE_SEL)));
  const sum = t.getCompactSummary();
  assert.equal(sum.clickCount, 0);
  assert.equal(sum.recentClicks.length, 0);
  assert.equal(sum.recentInteractions.length, 0);
});

test('data-genui-redact: shape captured, content dropped', () => {
  const t = newTracker();
  t.handleClick(clickEvent(el({ textContent: 'premium €12.000/year', href: '/quote/9' }, REDACT_SEL)));
  const sum = t.getCompactSummary();
  assert.equal(sum.clickCount, 1); // the shape (click, tag, id) is kept
  assert.equal(sum.recentInteractions.length, 1);
  assert.equal(sum.recentInteractions[0].elementId, 'promo-card');
  assert.equal(sum.recentInteractions[0].metadata.text, undefined);
  assert.equal(sum.recentInteractions[0].metadata.href, undefined);
});

test('form field content never captured, even with privacy off', () => {
  for (const privacy of ['strict', 'balanced', 'off']) {
    const t = newTracker({ privacy });
    t.handleClick(clickEvent(el({ tagName: 'TEXTAREA', textContent: 'my medical history' })));
    const sum = t.getCompactSummary();
    assert.equal(sum.recentInteractions.length, 1, privacy);
    assert.equal(sum.recentInteractions[0].metadata.text, undefined, privacy);
  }
});

test('balanced (default): text captured but PII redacted', () => {
  const t = newTracker(); // no privacy option = balanced
  t.handleClick(clickEvent(el({ textContent: 'Quote for mario.rossi@gmail.com — IBAN IT60X0542811101000000123456' })));
  const text = t.getCompactSummary().recentInteractions[0].metadata.text;
  assert.equal(text.includes('mario.rossi@gmail.com'), false);
  assert.equal(text.includes('IT60X0542811101000000123456'), false);
  assert.equal(text.includes('[redacted]'), true);
});

test('balanced: PII redacted before the 50-char truncation (no partial leak)', () => {
  const long = 'x'.repeat(40) + ' 4111 1111 1111 1111 end';
  const t = newTracker();
  t.handleClick(clickEvent(el({ textContent: long })));
  const text = t.getCompactSummary().recentInteractions[0].metadata.text;
  assert.equal(/\d{4}/.test(text), false);
  assert.ok(text.length <= 50);
});

test('strict: no free text leaves — no click text, no href, no title, no referrer', () => {
  const t = newTracker({ privacy: 'strict' });
  t.handleClick(clickEvent(el({ textContent: 'hello world', href: 'https://x.com/u/1' })));
  t.trackNavigation('/orders/12345678901', 'Order — Mario Rossi');
  const sum = t.getCompactSummary();
  assert.equal(sum.recentInteractions[0].metadata.text, undefined);
  assert.equal(sum.recentInteractions[0].metadata.href, undefined);
  // navigation paths are structural signals: kept, but PII-redacted
  assert.equal(sum.navigationPath.at(-1), '/orders/[redacted]');
  const page = t.record.metrics.navigationPattern.at(-1);
  assert.equal(page.includes('Mario'), false);
});

test('off: raw capture (explicit opt-out of redaction)', () => {
  const t = newTracker({ privacy: 'off' });
  t.handleClick(clickEvent(el({ textContent: 'mail a@b.com' })));
  t.trackNavigation('/u/a@b.com');
  const sum = t.getCompactSummary();
  assert.equal(sum.recentInteractions[0].metadata.text, 'mail a@b.com');
  assert.equal(sum.navigationPath.at(-1), '/u/a@b.com');
});

test('navigation: path and title redacted in balanced', () => {
  const t = newTracker();
  t.trackNavigation('/polizze/mario.rossi@gmail.com/rinnovo', 'Rinnovo — mario.rossi@gmail.com');
  const sum = t.getCompactSummary();
  assert.equal(sum.navigationPath.at(-1), '/polizze/[redacted]/rinnovo');
  const page = t.currentPage;
  assert.equal(page.title.includes('@'), false);
});

test('public trackInteraction: host metadata passes through the same filter', () => {
  const t = newTracker();
  t.trackInteraction('cta', 'button', 'click', {
    note: 'user typed mario.rossi@gmail.com',
    nested: { phone: '333 123 4567' },
    count: 2,
  });
  const meta = t.getCompactSummary().recentInteractions[0].metadata;
  assert.equal(meta.note.includes('@'), false);
  assert.equal(meta.nested.phone, '[redacted]');
  assert.equal(meta.count, 2);
});

test('getPrivacyLevel: exposed for callers that ship data (useZone)', () => {
  assert.equal(newTracker().getPrivacyLevel(), 'balanced');
  assert.equal(newTracker({ privacy: 'strict' }).getPrivacyLevel(), 'strict');
  assert.equal(newTracker({ privacy: 'off' }).getPrivacyLevel(), 'off');
});
