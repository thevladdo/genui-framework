// @vitest-environment jsdom
/**
 * meta.sanitization contract (built package): what the backend guarantee
 * chain removed (removed_urls, dropped_components, removed_numbers,
 * policy_violations) is exposed by useZone as camelCase meta.sanitization,
 * so a host can observe guarantee enforcement without parsing raw wire data.
 */

import { test, expect, vi } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { useZone } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const renderPayload = {
  zone_id: 'z',
  contract_version: 1,
  components: [{ type: 'text', data: { content: 'hi' } }],
  pinned_content_included: [],
  personalization_applied: false,
  meta: {
    confidence: 0.9,
    reasoning: '',
    profile_factors: [],
    render_id: 'r1',
    cache: { status: 'miss', strategy: 'segment', segment: 's' },
    sanitization: {
      removed_urls: ['https://evil.example/x'],
      dropped_components: [],
      removed_numbers: ['5M'],
      policy_violations: ['guaranteed returns'],
    },
  },
  rendered_at: '2026-07-18T00:00:00Z',
};

vi.stubGlobal('fetch', () =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(renderPayload) })
);

let captured: ReturnType<typeof useZone> | null = null;
const Probe: React.FC = () => {
  captured = useZone({ apiUrl: 'http://backend.test', zoneId: 'z' });
  return null;
};

test('useZone exposes meta.sanitization camelCase', async () => {
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => {
    root.render(<Probe />);
  });
  await vi.waitFor(() => expect(captured?.meta).not.toBeNull());

  expect(captured!.meta!.sanitization).toEqual({
    removedUrls: ['https://evil.example/x'],
    droppedComponents: [],
    removedNumbers: ['5M'],
    policyViolations: ['guaranteed returns'],
  });

  act(() => root.unmount());
});
