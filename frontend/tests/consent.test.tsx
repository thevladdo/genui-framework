// @vitest-environment jsdom
/**
 * Consent contract of a zone, against the BUILT package.
 *
 * Without an explicit grant the zone must be able to run on a page in
 * the EU without a banner: nothing stored on or read from the visitor's
 * device, no identifier and no behavior in the request. It must also
 * still render, because the degraded mode is a product level (content
 * curated for an anonymous segment), not an outage.
 *
 * With the grant, the previous behavior comes back unchanged.
 */

import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { GenUIZone, getBehaviorTracker, stopBehaviorTracker } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const RESPONSE = {
  zone_id: 'home',
  components: [{ type: 'text', data: { content: 'Curated for this segment' } }],
  pinned_content_included: [],
  personalization_applied: false,
  rendered_at: '2026-07-27T00:00:00+00:00',
  meta: { confidence: 0.8, reasoning: '', profile_factors: [], render_id: 'r1' },
};

let bodies: any[] = [];
/** Every property read on the global indexedDB, i.e. every terminal access */
let idbAccess: string[] = [];
let root: Root | null = null;
let container: HTMLDivElement;

beforeEach(() => {
  bodies = [];
  idbAccess = [];
  vi.stubGlobal('fetch', (_url: string, init: any) => {
    bodies.push(JSON.parse(init.body));
    return Promise.resolve({ ok: true, json: async () => RESPONSE });
  });
  // A real IndexedDB is not needed: the question is whether the library
  // reaches for it at all, so the stub records the attempt and fails.
  vi.stubGlobal(
    'indexedDB',
    new Proxy(
      {},
      {
        get(_target, prop) {
          idbAccess.push(String(prop));
          return () => {
            throw new Error('IndexedDB touched');
          };
        },
      }
    )
  );
  // jsdom has no IntersectionObserver; the zone uses one for impressions
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      disconnect() {}
    }
  );
  container = document.createElement('div');
  document.body.appendChild(container);
});

afterEach(async () => {
  if (root) await act(async () => root!.unmount());
  root = null;
  container.remove();
  stopBehaviorTracker();
  vi.unstubAllGlobals();
});

const mount = async (props: Record<string, unknown>) => {
  root = createRoot(container);
  await act(async () => {
    root!.render(
      React.createElement(GenUIZone, {
        apiUrl: 'http://backend.test',
        zoneId: 'home',
        userId: 'u-42',
        ...props,
      } as any)
    );
  });
  // Let the render promise chain settle before reading what was sent
  await act(async () => {
    await Promise.resolve();
  });
};

test('no consent: nothing on the device, nobody named, and it still renders', async () => {
  await mount({});

  expect(idbAccess).toEqual([]);
  expect(getBehaviorTracker()).toBeNull();

  const body = bodies[0];
  expect(body.user_id).toBeUndefined();
  expect(body.user_profile).toBeNull();
  expect(body.behavior_data).toBeNull();

  expect(container.textContent).toContain('Curated for this segment');
});

test('no consent: an explicit denial behaves like an unset one', async () => {
  await mount({ consent: false });

  expect(idbAccess).toEqual([]);
  expect(getBehaviorTracker()).toBeNull();
  expect(bodies[0].user_id).toBeUndefined();
  expect(container.textContent).toContain('Curated for this segment');
});

test('consent granted: profile read, identity sent, behavior collected', async () => {
  await mount({ consent: true });

  // The profile lookup reaches IndexedDB (the stub makes it fail, which
  // the hook swallows: the point is that it was attempted)
  expect(idbAccess).toContain('open');
  expect(bodies[0].user_id).toBe('u-42');
  expect(container.textContent).toContain('Curated for this segment');

  // A zone on its own starts the page tracker once consent is granted:
  // before, capture only ever started from useGenUI, so a page built
  // out of zones silently collected nothing.
  const tracker = getBehaviorTracker();
  expect(tracker).not.toBeNull();
  expect(tracker!.getPrivacyLevel()).toBe('balanced');
  expect(bodies[0].behavior_data).not.toBeNull();
});

test('consent granted with a stricter capture level', async () => {
  await mount({ consent: true, privacy: 'strict' });
  expect(getBehaviorTracker()!.getPrivacyLevel()).toBe('strict');
});
