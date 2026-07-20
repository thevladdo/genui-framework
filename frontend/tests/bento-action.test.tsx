// @vitest-environment jsdom
/**
 * BentoCard.action contract (built package): the backend schema emits an
 * optional per-card action button (CardAction: label + url) and the FE
 * type declares it — BentoComponent must render it. The URL goes through
 * sanitizeUrl (defense in depth: an unsafe scheme drops the button, a
 * dead CTA is worse than none). Without an action, no button appears.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { BentoComponent } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const render = async (cards: any[]) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(<BentoComponent data={{ cards }} />);
  });
  return { container, root };
};

test('card action renders as a sanitized link button', async () => {
  const { container, root } = await render([
    { title: 'Plan', action: { label: 'Buy now', url: 'https://ok.example/buy' } },
  ]);

  const action = container.querySelector('a.genui-bento-card__action');
  expect(action).not.toBeNull();
  expect(action!.getAttribute('href')).toBe('https://ok.example/buy');
  expect(action!.textContent).toBe('Buy now');

  act(() => root.unmount());
});

test('action with a dangerous URL is dropped entirely', async () => {
  const { container, root } = await render([
    { title: 'Plan', action: { label: 'Buy', url: 'javascript:alert(1)' } },
  ]);

  expect(container.querySelector('.genui-bento-card__action')).toBeNull();

  act(() => root.unmount());
});

test('card without action renders no action button', async () => {
  const { container, root } = await render([{ title: 'Plan', description: 'd' }]);

  expect(container.querySelector('.genui-bento-card__action')).toBeNull();

  act(() => root.unmount());
});

test('card with both link and action keeps a single non-nested anchor', async () => {
  const { container, root } = await render([
    {
      title: 'Plan',
      link: 'https://ok.example/card',
      action: { label: 'Buy', url: 'https://ok.example/buy' },
    },
  ]);

  // Nested <a> is invalid HTML and gets split by SSR parsers: the action
  // takes over as the card's interactive element.
  expect(container.querySelector('a a')).toBeNull();
  const action = container.querySelector('a.genui-bento-card__action');
  expect(action!.getAttribute('href')).toBe('https://ok.example/buy');

  act(() => root.unmount());
});

test('columns are capped by card count (1 card never gets a 3-col grid)', async () => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <BentoComponent data={{ cards: [{ title: 'Only card' }], columns: 3 }} />,
    );
  });

  const grid = container.querySelector('.genui-bento');
  expect(grid!.className).toContain('genui-bento--cols-1');
  expect(grid!.className).not.toContain('genui-bento--cols-3');

  act(() => root.unmount());
});

test('columns stay as requested when there are enough cards', async () => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <BentoComponent
        data={{
          cards: [{ title: 'A' }, { title: 'B' }, { title: 'C' }],
          columns: 3,
        }}
      />,
    );
  });

  expect(container.querySelector('.genui-bento')!.className).toContain(
    'genui-bento--cols-3',
  );

  act(() => root.unmount());
});
