// @vitest-environment jsdom
/**
 * Identity and consent are the scope of every piece of state the library keeps in memory.
 * When either changes, what belonged to the previous scope is dropped, responses still in flight included, and the next request carries nothing from it.
 */

import 'fake-indexeddb/auto';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import {
  GenUIZone,
  getBehaviorTracker,
  stopBehaviorTracker,
  useGenUI,
} from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const ZONE_RESPONSE = {
  zone_id: 'home',
  components: [{ type: 'text', data: { content: 'zone content' } }],
  pinned_content_included: [],
  personalization_applied: true,
  rendered_at: '2026-09-27T00:00:00+00:00',
  meta: { confidence: 0.8, reasoning: '', profile_factors: [], render_id: 'r1' },
};

const chatResponse = (text: string) => ({
  text,
  components: [],
  profile_updates: {
    should_update: true,
    updates: [
      {
        field: 'interests.topic',
        value: `learned from ${text}`,
        confidence: 0.9,
        source: 'chat',
        timestamp: '2026-09-27T00:00:00Z',
      },
    ],
  },
  meta: {},
});

type Call = { url: string; body: any };
let calls: Call[] = [];
/** When set, the next /query stays pending until the test resolves it */
let holdNextQuery: ((release: (r: Response) => void) => void) | null = null;
let root: Root | null = null;
let container: HTMLDivElement;

beforeEach(() => {
  calls = [];
  holdNextQuery = null;
  vi.stubGlobal('fetch', (url: string, init: any) => {
    const body = JSON.parse(init.body);
    calls.push({ url, body });
    if (url.endsWith('/api/v1/query')) {
      if (holdNextQuery) {
        const hold = holdNextQuery;
        holdNextQuery = null;
        return new Promise<Response>((resolve, reject) => {
          init.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          );
          hold(resolve);
        });
      }
      return Promise.resolve(new Response(JSON.stringify(chatResponse(body.query))));
    }
    return Promise.resolve(new Response(JSON.stringify(ZONE_RESPONSE)));
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
});

afterEach(async () => {
  if (root) await act(async () => root!.unmount());
  root = null;
  container.remove();
  stopBehaviorTracker();
  vi.unstubAllGlobals();
});

const settle = async () => {
  for (let i = 0; i < 10; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
};

let chat: ReturnType<typeof useGenUI>;
const onProfileUpdate = vi.fn();

const Chat: React.FC<{ userId: string; consent?: boolean; apiUrl?: string }> = ({
  userId,
  consent,
  apiUrl = 'http://backend.test',
}) => {
  chat = useGenUI({ apiUrl, userId, consent, onProfileUpdate });
  return null;
};

const render = async (node: React.ReactElement) => {
  if (!root) root = createRoot(container);
  await act(async () => root!.render(node));
  await settle();
};

const queryBodies = () => calls.filter((c) => c.url.endsWith('/api/v1/query')).map((c) => c.body);

test('(a) a new userId starts a clean session: no history, profile or late answer of the previous user', async () => {
  await render(<Chat userId="alice" consent />);
  await act(async () => {
    await chat.query('first from alice');
  });
  await settle();
  expect(chat.history.length).toBe(2);
  expect(chat.profile?.interests.topic?.value).toBe('learned from first from alice');

  // A second question from alice is still in flight when the user changes
  let release!: (r: Response) => void;
  holdNextQuery = (r) => {
    release = r;
  };
  let late!: Promise<unknown>;
  await act(async () => {
    late = chat.query('second from alice').catch((e) => e);
  });
  await settle();
  expect(typeof release).toBe('function');
  const aliceSession = queryBodies()[0].behavior_data.sessionId;

  await render(<Chat userId="bob" consent />);
  onProfileUpdate.mockClear();

  // alice's answer arrives after the switch: it must land nowhere
  await act(async () => {
    release(new Response(JSON.stringify(chatResponse('late for alice'))));
  });
  expect(await late).toMatchObject({ name: 'AbortError' });
  await settle();
  expect(chat.history).toEqual([]);
  expect(onProfileUpdate).not.toHaveBeenCalled();
  expect(chat.profile?.userId).toBe('bob');

  await act(async () => {
    await chat.query('hello from bob');
  });
  const bobFirst = queryBodies().at(-1);
  expect(bobFirst.user_id).toBe('bob');
  expect(bobFirst.conversation_history).toEqual([]);
  expect(bobFirst.user_profile.userId).toBe('bob');
  expect(bobFirst.user_profile.interests).toEqual({});
  expect(bobFirst.behavior_data.userId).toBe('bob');
  expect(bobFirst.behavior_data.sessionId).not.toBe(aliceSession);
});

test('(a) a new backend is a new identity too', async () => {
  await render(<Chat userId="alice" consent apiUrl="http://a.test" />);
  await act(async () => {
    await chat.query('to backend a');
  });
  await render(<Chat userId="alice" consent apiUrl="http://b.test" />);
  await act(async () => {
    await chat.query('to backend b');
  });
  const toB = queryBodies().at(-1);
  expect(toB.conversation_history).toEqual([]);
  expect(toB.user_profile.interests).toEqual({});
});

test('(b) revoking consent mid-session: tracker stopped, nothing identifying in the next request', async () => {
  await render(<Chat userId="alice" consent />);
  await act(async () => {
    await chat.query('with consent');
  });
  expect(getBehaviorTracker()).not.toBeNull();
  expect(chat.profile).not.toBeNull();

  await render(<Chat userId="alice" consent={false} />);
  expect(getBehaviorTracker()).toBeNull();
  expect(chat.profile).toBeNull();
  expect(chat.history).toEqual([]);

  await act(async () => {
    await chat.query('without consent');
  });
  const body = queryBodies().at(-1);
  expect(body.user_id).toBeUndefined();
  expect(body.user_profile).toBeNull();
  expect(body.behavior_data).toBeNull();
  expect(body.conversation_history).toEqual([]);
  expect(JSON.stringify(body)).not.toContain('alice');
});

test('(b) revoking consent on a zone stops the page tracker it started', async () => {
  const zone = (consent: boolean) => (
    <GenUIZone apiUrl="http://backend.test" zoneId="home" userId="alice" consent={consent} />
  );
  await render(zone(true));
  expect(getBehaviorTracker()).not.toBeNull();

  await render(zone(false));
  expect(getBehaviorTracker()).toBeNull();
  const last = calls.filter((c) => c.url.includes('/zone/render')).at(-1)!.body;
  expect(last.user_id).toBeUndefined();
  expect(last.user_profile).toBeNull();
  expect(last.behavior_data).toBeNull();
});

test('(c) a chat without consent does not read the tracker a consented zone started', async () => {
  await render(
    <>
      <GenUIZone apiUrl="http://backend.test" zoneId="home" userId="alice" consent />
      <Chat userId="alice" />
    </>,
  );
  expect(getBehaviorTracker()).not.toBeNull();

  await act(async () => {
    await chat.query('anonymous question');
  });
  const body = queryBodies().at(-1);
  expect(body.behavior_data).toBeNull();
  expect(body.user_profile).toBeNull();
  expect(body.user_id).toBeUndefined();
});

test('(c) a consented reader with another identity does not read the tracker either', async () => {
  await render(
    <>
      <GenUIZone apiUrl="http://backend.test" zoneId="home" userId="alice" consent />
      <Chat userId="bob" consent />
    </>,
  );
  await act(async () => {
    await chat.query('bob asks');
  });
  const body = queryBodies().at(-1);
  expect(body.behavior_data?.userId).not.toBe('alice');
});

test('(c) a reader that starts no tracker of its own does not read another user\'s', async () => {
  let untracked!: ReturnType<typeof useGenUI>;
  const UntrackedChat: React.FC = () => {
    untracked = useGenUI({
      apiUrl: 'http://backend.test',
      userId: 'bob',
      consent: true,
      enableBehaviorTracking: false,
    });
    return null;
  };
  await render(
    <>
      <GenUIZone apiUrl="http://backend.test" zoneId="home" userId="alice" consent />
      <UntrackedChat />
    </>,
  );
  expect(getBehaviorTracker()).not.toBeNull();

  await act(async () => {
    await untracked.query('bob asks without tracking');
  });
  expect(queryBodies().at(-1).behavior_data).toBeNull();
});

test('(b) clearing the profile without consent sends nothing identifying', async () => {
  await render(<Chat userId="alice" />);
  await act(async () => {
    await chat.clearProfile();
  });
  expect(chat.profile?.userId).toBe('alice');

  await act(async () => {
    await chat.query('after erasing my data');
  });
  const body = queryBodies().at(-1);
  expect(body.user_profile).toBeNull();
  expect(body.user_id).toBeUndefined();
  expect(JSON.stringify(body)).not.toContain('alice');
});
