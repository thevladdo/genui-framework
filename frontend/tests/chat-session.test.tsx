// @vitest-environment jsdom
/**
 * The backend remembers the conversation, the client shows it.
 * The chat sends the session id and the new message only; the id survives a reload only with consent, and never passes to another identity.
 */

import 'fake-indexeddb/auto';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { stopBehaviorTracker, useGenUI } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

type Call = { url: string; method: string; body: any };
let calls: Call[] = [];
let minted = 0;
let deleteStatus = 200;
let root: Root | null = null;
let container: HTMLDivElement;

beforeEach(() => {
  calls = [];
  deleteStatus = 200;
  sessionStorage.clear();
  vi.stubGlobal('fetch', (url: string, init: any) => {
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(init.body) : null;
    calls.push({ url, method, body });
    if (method === 'DELETE') {
      return Promise.resolve(
        new Response(JSON.stringify(deleteStatus === 200 ? { deleted: true } : { detail: 'store down' }), {
          status: deleteStatus,
        }),
      );
    }
    const sessionId = body.session_id ?? `session-${String(++minted).padStart(12, '0')}`;
    return Promise.resolve(
      new Response(
        JSON.stringify({
          session_id: sessionId,
          text: `answer to ${body.query}`,
          components: [],
          profile_updates: { should_update: false, updates: [] },
          meta: { session: { resumed: Boolean(body.session_id), stored: true, unsummarized: 0 } },
        }),
      ),
    );
  });
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

const Chat: React.FC<{ userId: string; consent?: boolean }> = ({ userId, consent }) => {
  chat = useGenUI({ apiUrl: 'http://backend.test', userId, consent, enableBehaviorTracking: false });
  return null;
};

const render = async (node: React.ReactElement) => {
  if (!root) root = createRoot(container);
  await act(async () => root!.render(node));
  await settle();
};

const reload = async (node: React.ReactElement) => {
  if (root) await act(async () => root!.unmount());
  root = null;
  await render(node);
};

const ask = async (text: string) => {
  let answer!: Awaited<ReturnType<typeof chat.query>>;
  await act(async () => {
    answer = await chat.query(text);
  });
  await settle();
  return answer;
};

const queries = () => calls.filter((c) => c.url.endsWith('/api/v1/query')).map((c) => c.body);

test('only the session id and the new message travel', async () => {
  await render(<Chat userId="ann" consent />);
  await ask('first');
  await ask('second');

  const [first, second] = queries();
  expect(first.session_id).toBeUndefined();
  expect(second.session_id).toBe('session-' + String(minted).padStart(12, '0'));
  expect(second.query).toBe('second');
  expect('conversation_history' in second).toBe(false);
  expect(chat.history.map((m) => m.content)).toEqual([
    'first', 'answer to first', 'second', 'answer to second',
  ]);
});

test('(f) a reload with consent resumes the session and shows its history', async () => {
  await render(<Chat userId="cara" consent />);
  const { sessionId } = await ask('before reload');
  expect(sessionId).toBeDefined();
  expect(sessionStorage.length).toBe(1);

  await reload(<Chat userId="cara" consent />);
  expect(chat.history.map((m) => m.content)).toEqual(['before reload', 'answer to before reload']);
  await ask('after reload');
  expect(queries().at(-1).session_id).toBe(sessionId);
});

test('(f) without consent nothing is kept and a reload starts over', async () => {
  await render(<Chat userId="dan" />);
  await ask('one');
  await ask('two');
  expect(queries()[1].session_id).toBeDefined();
  expect(sessionStorage.length).toBe(0);

  await reload(<Chat userId="dan" />);
  expect(chat.history).toEqual([]);
  await ask('three');
  expect(queries().at(-1).session_id).toBeUndefined();
});

test('(f) a change of identity discards the session, in memory and in storage', async () => {
  await render(<Chat userId="eve" consent />);
  await ask('eve speaks');
  await ask('eve again');
  const eveSession = queries()[1].session_id;

  await render(<Chat userId="finn" consent />);
  await ask('finn speaks');
  expect(queries().at(-1).session_id).toBeUndefined();
  expect(JSON.stringify(sessionStorage)).not.toContain(eveSession);

  await render(<Chat userId="eve" consent={false} />);
  expect(sessionStorage.length).toBe(0);
  await ask('eve without consent');
  expect(queries().at(-1).session_id).toBeUndefined();

  await reload(<Chat userId="eve" consent />);
  await ask('eve back');
  expect(queries().at(-1).session_id).toBeUndefined();
});

test('clearHistory deletes the session on the backend before forgetting it', async () => {
  await render(<Chat userId="gil" consent />);
  await ask('to forget');
  await ask('again');
  const sessionId = queries()[1].session_id;

  deleteStatus = 503;
  await act(async () => {
    await expect(chat.clearHistory()).rejects.toMatchObject({ status: 503 });
  });
  expect(chat.history.length).toBe(4);
  await ask('still remembered');
  expect(queries().at(-1).session_id).toBe(sessionId);

  deleteStatus = 200;
  await act(async () => {
    await chat.clearHistory();
  });
  const deletes = calls.filter((c) => c.method === 'DELETE').map((c) => c.url);
  expect(deletes.at(-1)).toBe(`http://backend.test/api/v1/query/sessions/${sessionId}`);
  expect(chat.history).toEqual([]);
  expect(sessionStorage.length).toBe(0);

  await ask('fresh start');
  expect(queries().at(-1).session_id).toBeUndefined();
});

test('(f) a page loaded by another identity does not pick up the stored session', async () => {
  await render(<Chat userId="hal" consent />);
  await ask('hal speaks');
  expect(sessionStorage.length).toBe(1);

  await reload(<Chat userId="ivy" consent />);
  expect(chat.history).toEqual([]);
  expect(sessionStorage.length).toBe(0);
  await ask('ivy speaks');
  expect(queries().at(-1).session_id).toBeUndefined();
});

test('(f) a page loaded without consent leaves no stored session of the previous visitor', async () => {
  await render(<Chat userId="hal" consent />);
  await ask('hal speaks');
  const halSession = JSON.parse(sessionStorage.getItem(sessionStorage.key(0)!)!).sessionId;

  await reload(<Chat userId="joy" />);
  expect(JSON.stringify(sessionStorage)).not.toContain(halSession);
});
