// @vitest-environment jsdom
/**
 * Reactive props contract for useZone (built package):
 *  - changing zoneId refetches and ABORTS the inflight request (last wins)
 *  - re-rendering with equal-by-value props (fresh object literals) does
 *    NOT refetch: no fetch loop from hosts passing inline arrays/objects
 */

import { test, expect, vi } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { useZone } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

type RecordedCall = { url: string; body: any; signal: AbortSignal };
const calls: RecordedCall[] = [];

// Never resolves (keeps the request inflight); rejects on abort like real fetch
vi.stubGlobal('fetch', (url: string, init: any) => {
  calls.push({ url, body: JSON.parse(init.body), signal: init.signal });
  return new Promise((_resolve, reject) => {
    init.signal?.addEventListener('abort', () =>
      reject(new DOMException('Aborted', 'AbortError'))
    );
  });
});

const Probe: React.FC<{ zoneId: string }> = ({ zoneId }) => {
  useZone({
    apiUrl: 'http://backend.test',
    zoneId,
    userId: 'u1',
    // Fresh literal on EVERY render: must not cause a refetch by itself
    pinnedContent: [{ type: 'link', url: '/a', title: 'A' }],
  });
  return null;
};

test('zoneId change refetches with abort; equal-value re-render does not', async () => {
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => {
    root.render(<Probe zoneId="zone-a" />);
  });
  await vi.waitFor(() => expect(calls.length).toBe(1));
  expect(calls[0].body.zone_id).toBe('zone-a');

  // Same values, new object identities: no refetch (no fetch loop)
  await act(async () => {
    root.render(<Probe zoneId="zone-a" />);
  });
  await act(async () => {
    await Promise.resolve();
  });
  expect(calls.length).toBe(1);

  // zoneId changes: the inflight request is aborted, a new one is issued
  await act(async () => {
    root.render(<Probe zoneId="zone-b" />);
  });
  await vi.waitFor(() => expect(calls.length).toBe(2));
  expect(calls[0].signal.aborted).toBe(true);
  expect(calls[1].body.zone_id).toBe('zone-b');
  expect(calls[1].signal.aborted).toBe(false);

  // Unmount aborts the survivor too
  act(() => root.unmount());
  expect(calls[1].signal.aborted).toBe(true);
});
