// @vitest-environment jsdom
/**
 * stats_banner: what the extension must not change and what it adds.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { StatsBanner } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

const OLD_PAYLOAD = {
  stats: [
    { value: '10M', label: 'Users reached' },
    { value: '99.9%', label: 'Uptime', description: 'last 12 months' },
  ],
  columns: 2 as const,
};

test('the payload that worked before renders the same markup', async () => {
  const { container, root } = await mount(<StatsBanner data={OLD_PAYLOAD} />);
  const section = container.querySelector('.genui-stats') as HTMLElement;

  expect(section.className).toBe('genui-stats');
  expect(section.style.getPropertyValue('--genui-stats-cols')).toBe('2');
  expect([...section.children].every((c) => c.className === 'genui-stats__item')).toBe(true);
  expect(container.querySelector('.genui-stats__movement')).toBeNull();
  expect(container.querySelector('.genui-stats__intro')).toBeNull();
  act(() => root.unmount());
});

test('split puts the narration beside the grid', async () => {
  const { container, root } = await mount(
    <StatsBanner
      data={{
        ...OLD_PAYLOAD,
        layout: 'split',
        eyebrow: 'Platform',
        title: 'This is the start of something new',
        description: 'What the numbers count.',
      }}
    />,
  );
  expect(container.querySelector('.genui-stats--split')).not.toBeNull();
  expect(container.querySelector('.genui-stats__eyebrow')?.textContent).toBe('Platform');
  expect(container.querySelector('h2')?.textContent).toBe('This is the start of something new');
  expect(container.querySelectorAll('.genui-stats__grid .genui-stats__item').length).toBe(2);
  act(() => root.unmount());
});

test('split with nothing to put beside the grid falls back to the grid', async () => {
  const { container, root } = await mount(
    <StatsBanner data={{ ...OLD_PAYLOAD, layout: 'split' }} />,
  );
  expect(container.querySelector('.genui-stats--split')).toBeNull();
  expect(container.querySelectorAll('.genui-stats__item').length).toBe(2);
  act(() => root.unmount());
});

test('a movement shows the direction and the delta next to the value', async () => {
  const { container, root } = await mount(
    <StatsBanner
      data={{
        stats: [
          {
            value: '500,000',
            label: 'Monthly active users',
            change: { direction: 'up', value: '+20.1%', sentiment: 'good' },
          },
        ],
      }}
    />,
  );
  expect(container.querySelector('.genui-stats__change')?.textContent).toBe('+20.1%');
  expect(container.querySelector('.genui-stats__item--good')).not.toBeNull();
  expect(container.querySelector('.genui-stats__movement svg')).not.toBeNull();
  act(() => root.unmount());
});

test('a direction with no sentiment stays neutral', async () => {
  const { container, root } = await mount(
    <StatsBanner
      data={{
        stats: [
          {
            value: '1,052',
            label: 'Cost per acquisition',
            change: { direction: 'down', value: '-2%' },
          },
        ],
      }}
    />,
  );
  const item = container.querySelector('.genui-stats__item')!;
  expect(item.className).toBe('genui-stats__item');
  expect(item.className).not.toContain('bad');
  expect(container.querySelector('.genui-stats__movement')).not.toBeNull();
  act(() => root.unmount());
});

test('the direction is readable without seeing the arrow', async () => {
  const { container, root } = await mount(
    <StatsBanner
      data={{ stats: [{ value: '20,105', label: 'Daily users', change: { direction: 'down' } }] }}
    />,
  );
  expect(container.querySelector('.genui-sr-only')?.textContent).toBe('down');
  expect(container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
  act(() => root.unmount());
});

test('the arrow shape differs by direction, not only its color', async () => {
  const up = await mount(
    <StatsBanner data={{ stats: [{ value: '1', label: 'A', change: { direction: 'up' } }] }} />,
  );
  const down = await mount(
    <StatsBanner data={{ stats: [{ value: '1', label: 'A', change: { direction: 'down' } }] }} />,
  );
  const shape = (c: HTMLElement) =>
    [...c.querySelectorAll('svg path')].map((p) => p.getAttribute('d')).join('|');
  expect(shape(up.container)).not.toBe(shape(down.container));
  act(() => up.root.unmount());
  act(() => down.root.unmount());
});
