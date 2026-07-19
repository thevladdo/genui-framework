// @vitest-environment jsdom
/**
 * meta.behavior contract (built package): when the backend orchestrator
 * attaches behavior analysis to /query responses (engagement_score,
 * user_type, session_summary, insights_count, ui_adjustments), useGenUI
 * must expose it as camelCase meta.behavior — same choke point and same
 * pattern as the meta.sanitization mapping. Without behavior in the
 * payload, meta.behavior stays undefined.
 */

import { test, expect, vi } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { useGenUI } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const queryPayload = (withBehavior: boolean) => ({
  contract_version: 1,
  text: 'hi',
  components: [],
  sources: [],
  suggested_actions: [],
  profile_updates: { should_update: false, updates: [] },
  meta: {
    confidence: 0.9,
    interaction_type: 'question',
    topics: [],
    sentiment: 'neutral',
    ...(withBehavior
      ? {
          behavior: {
            engagement_score: 0.72,
            user_type: 'explorer',
            session_summary: 'browsing pricing pages',
            insights_count: 2,
            ui_adjustments: [
              { type: 'layout', target: 'zone', suggestion: 'denser' },
            ],
          },
        }
      : {}),
  },
});

let captured: ReturnType<typeof useGenUI> | null = null;
const Probe: React.FC = () => {
  captured = useGenUI({
    apiUrl: 'http://backend.test',
    enablePersistence: false,
    enableBehaviorTracking: false,
  });
  return null;
};

const renderProbe = async () => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(<Probe />);
  });
  return root;
};

test('useGenUI exposes meta.behavior camelCase when the backend sends it', async () => {
  vi.stubGlobal('fetch', () =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(queryPayload(true)) })
  );
  const root = await renderProbe();

  let response: Awaited<ReturnType<NonNullable<typeof captured>['query']>>;
  await act(async () => {
    response = await captured!.query('hello');
  });

  expect(response!.meta.behavior).toEqual({
    engagementScore: 0.72,
    userType: 'explorer',
    sessionSummary: 'browsing pricing pages',
    insightsCount: 2,
    uiAdjustments: [{ type: 'layout', target: 'zone', suggestion: 'denser' }],
  });

  act(() => root.unmount());
});

test('meta.behavior stays undefined when the backend omits it', async () => {
  vi.stubGlobal('fetch', () =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(queryPayload(false)) })
  );
  const root = await renderProbe();

  let response: Awaited<ReturnType<NonNullable<typeof captured>['query']>>;
  await act(async () => {
    response = await captured!.query('hello');
  });

  expect(response!.meta.behavior).toBeUndefined();

  act(() => root.unmount());
});
