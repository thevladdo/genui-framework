// @vitest-environment jsdom
/**
 * How a zone fails: a stream cut short is an error, a hostile payload key costs one component and not the zone, and an error says enough (HTTP status, Retry-After) for the host to pick its own fallback.
 * The library itself never retries.
 */

import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import {
  ComponentRenderer,
  GenUIError,
  GenUIZone,
  registerGenUIComponent,
  useZone,
} from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const COMPLETE = {
  zone_id: 'z',
  components: [{ type: 'text', data: { content: 'final' } }],
  pinned_content_included: [],
  personalization_applied: false,
  rendered_at: '2026-09-27T00:00:00+00:00',
  meta: { render_id: 'r-previous' },
};

const sse = (...events: Array<[string, unknown]>) =>
  new Response(
    events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(''),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );

let responses: Array<() => Response> = [];
let fetchCount = 0;
let root: Root | null = null;
let container: HTMLDivElement;

beforeEach(() => {
  responses = [];
  fetchCount = 0;
  vi.stubGlobal('fetch', () => {
    fetchCount++;
    const next = responses.shift();
    if (!next) throw new Error('unexpected fetch');
    return Promise.resolve(next());
  });
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      disconnect() {}
    },
  );
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  if (root) await act(async () => root!.unmount());
  root = null;
  container.remove();
  vi.unstubAllGlobals();
});

const settle = async () => {
  for (let i = 0; i < 10; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
};

let zone: ReturnType<typeof useZone>;
const Probe: React.FC<{ onRender: (c: unknown[]) => void; onError: (e: Error) => void }> = (
  props,
) => {
  zone = useZone({ apiUrl: 'http://backend.test', zoneId: 'z', streaming: true, ...props });
  return null;
};

test('(d) a stream that closes without complete is an error, and onRender never sees the partials', async () => {
  const onRender = vi.fn();
  const onError = vi.fn();
  responses.push(() => sse(['component', { type: 'text', data: { content: 'x' } }], ['complete', COMPLETE]));
  await act(async () => root!.render(<Probe onRender={onRender} onError={onError} />));
  await settle();
  expect(zone.meta?.renderId).toBe('r-previous');
  expect(onRender).toHaveBeenCalledTimes(1);
  onRender.mockClear();

  responses.push(() =>
    sse(
      ['component', { type: 'text', data: { content: 'one' } }],
      ['component', { type: 'text', data: { content: 'two' } }],
    ),
  );
  await act(async () => {
    await zone.render();
  });
  await settle();

  expect(onRender).not.toHaveBeenCalled();
  expect(onError).toHaveBeenCalledTimes(1);
  expect(zone.error).toBeInstanceOf(GenUIError);
  expect(zone.components).toEqual([]);
  // A failed render must not leave the previous variant's identity around
  expect(zone.meta).toBeNull();
});

test('(e) a payload with hasOwnProperty as a key costs nothing: the zone renders every component', async () => {
  await act(async () =>
    root!.render(
      <ComponentRenderer
        components={[
          { type: 'text', data: { hasOwnProperty: 1, content: 'hostile key' } } as any,
          { type: 'text', data: { content: 'sibling' } } as any,
        ]}
      />,
    ),
  );
  expect(container.textContent).toContain('hostile key');
  expect(container.textContent).toContain('sibling');
});

test('(e) the component boundary resets when a new payload arrives', async () => {
  registerGenUIComponent('fragile', ({ data }: any) => {
    if (data.broken) throw new Error('bad payload');
    return <p>{data.label}</p>;
  });
  const quiet = vi.spyOn(console, 'error').mockImplementation(() => {});
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

  await act(async () =>
    root!.render(<ComponentRenderer components={[{ type: 'fragile', data: { broken: true } } as any]} />),
  );
  expect(container.textContent).toBe('');

  await act(async () =>
    root!.render(<ComponentRenderer components={[{ type: 'fragile', data: { label: 'recovered' } } as any]} />),
  );
  expect(container.textContent).toContain('recovered');
  quiet.mockRestore();
  warn.mockRestore();
});

const captured: GenUIError[] = [];
const mountZone = async (streaming = false) => {
  captured.length = 0;
  await act(async () =>
    root!.render(
      <GenUIZone
        apiUrl="http://backend.test"
        zoneId="z"
        streaming={streaming}
        errorComponent={(e) => {
          captured.push(e as GenUIError);
          return <p>site fallback</p>;
        }}
      />,
    ),
  );
  await settle();
};

test('(h) a 503 with Retry-After reaches errorComponent with status and retryAfter, and nothing retries', async () => {
  responses.push(
    () =>
      new Response(JSON.stringify({ detail: 'zone is being generated' }), {
        status: 503,
        headers: { 'Retry-After': '60', 'Content-Type': 'application/json' },
      }),
  );
  await mountZone();
  expect(container.textContent).toContain('site fallback');
  expect(captured.at(-1)).toMatchObject({ status: 503, retryAfter: 60 });
  expect(captured.at(-1)!.message).toBe('zone is being generated');

  await new Promise((r) => setTimeout(r, 50));
  await settle();
  expect(fetchCount).toBe(1);
});

test('(h) the same 503 as a stream error event carries status and retryAfter', async () => {
  responses.push(() =>
    sse(['error', { detail: 'store unreachable', status: 503, retry_after: '30', zone_id: 'z' }]),
  );
  await mountZone(true);
  expect(captured.at(-1)).toMatchObject({ status: 503, retryAfter: 30 });
  expect(fetchCount).toBe(1);
});

test('(h) a 500 arrives with its status and no retryAfter', async () => {
  responses.push(
    () =>
      new Response(JSON.stringify({ detail: 'boom' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
  await mountZone();
  expect(captured.at(-1)!.status).toBe(500);
  expect(captured.at(-1)!.retryAfter).toBeUndefined();
});
