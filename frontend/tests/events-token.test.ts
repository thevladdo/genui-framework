/**
 * UI events carry the signed identity when there is one: the backend keeps an event's user_id only when the token proves it.
 */

import { afterEach, expect, test, vi } from 'vitest';
import { sendGenUIEvents } from 'genui-framework';

afterEach(() => {
  vi.unstubAllGlobals();
});

const capture = () => {
  const calls: Array<{ url: string; init: any }> = [];
  vi.stubGlobal('fetch', (url: string, init: any) => {
    calls.push({ url, init });
    return Promise.resolve(new Response('{}'));
  });
  return calls;
};

const EVENT = { event_type: 'impression', zone_id: 'home', user_id: 'alice' };

test('the user token travels with the events', () => {
  const calls = capture();
  sendGenUIEvents('http://api', 'pk_x', [EVENT], 'signed.token');
  expect(calls).toHaveLength(1);
  expect(calls[0].url).toBe('http://api/api/v1/events');
  expect(calls[0].init.headers['X-User-Token']).toBe('signed.token');
});

test('no token, no header: the events still go out', () => {
  const calls = capture();
  sendGenUIEvents('http://api', 'pk_x', [EVENT]);
  expect(calls).toHaveLength(1);
  expect(calls[0].init.headers).not.toHaveProperty('X-User-Token');
});
