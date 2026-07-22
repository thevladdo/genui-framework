// @vitest-environment jsdom
/**
 * Grid components must never render more columns than they have items:
 * a 3-column grid with 1 item squeezes the card into a third of the zone
 * (the same defect fixed in BentoComponent). ContentGrid capped its
 * default columns by item count; StatsBanner caps even an explicit
 * model-sent column count.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ContentGrid, StatsBanner } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

test('ContentGrid caps columns at the item count', async () => {
  const { container, root } = await mount(
    <ContentGrid data={{ items: [{ title: 'Only one' }], columns: 3 }} />,
  );
  const grid = container.querySelector('.genui-contentgrid') as HTMLElement;
  expect(grid.style.getPropertyValue('--genui-content-cols')).toBe('1');
  act(() => root.unmount());
});

test('ContentGrid keeps the requested columns with enough items', async () => {
  const { container, root } = await mount(
    <ContentGrid
      data={{ items: [{ title: 'A' }, { title: 'B' }, { title: 'C' }], columns: 3 }}
    />,
  );
  const grid = container.querySelector('.genui-contentgrid') as HTMLElement;
  expect(grid.style.getPropertyValue('--genui-content-cols')).toBe('3');
  act(() => root.unmount());
});

test('StatsBanner caps an explicit column count by the stat count', async () => {
  const { container, root } = await mount(
    <StatsBanner
      data={{
        stats: [
          { label: 'Uptime', value: '99.9%' },
          { label: 'Users', value: '2k' },
        ],
        columns: 4,
      }}
    />,
  );
  const grid = container.querySelector('.genui-stats') as HTMLElement;
  expect(grid.style.getPropertyValue('--genui-stats-cols')).toBe('2');
  act(() => root.unmount());
});
