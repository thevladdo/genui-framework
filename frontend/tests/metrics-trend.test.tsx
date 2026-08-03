// @vitest-environment jsdom
/**
 * metrics_trend: the grid stands on its own and the curve is data.
 *
 * The backend decides which figures survive. What the component owes is the other half: a section that still reads when the series is gone.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MetricsTrend } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

const METRICS = [
  { value: '50,000', label: 'Teams' },
  { value: '99.9%', label: 'Uptime' },
];

const SERIES = [
  { label: 'Jan', value: 20 },
  { label: 'Feb', value: 60 },
  { label: 'Mar', value: 40 },
];

test('grid and curve render together', async () => {
  const { container, root } = await mount(
    <MetricsTrend data={{ title: 'Where we are', metrics: METRICS, series: SERIES }} />,
  );
  expect(container.querySelectorAll('.genui-metrics__item').length).toBe(2);
  expect(container.querySelector('.genui-metrics__curve')).not.toBeNull();
  act(() => root.unmount());
});

test('without a series the section is the grid, with no empty frame', async () => {
  const { container, root } = await mount(
    <MetricsTrend data={{ title: 'Where we are', metrics: METRICS, series: [] }} />,
  );
  expect(container.querySelectorAll('.genui-metrics__item').length).toBe(2);
  expect(container.querySelector('.genui-metrics__trend')).toBeNull();
  expect(container.querySelector('svg')).toBeNull();
  act(() => root.unmount());
});

test('a single point is not a curve', async () => {
  const { container, root } = await mount(
    <MetricsTrend
      data={{ title: 'T', metrics: METRICS, series: [{ label: 'Jan', value: 20 }] }}
    />,
  );
  expect(container.querySelector('.genui-metrics__trend')).toBeNull();
  act(() => root.unmount());
});

test('every point is readable without seeing the line', async () => {
  const { container, root } = await mount(
    <MetricsTrend data={{ title: 'T', metrics: METRICS, series: SERIES }} />,
  );
  const listed = [...container.querySelectorAll('.genui-sr-only li')].map(
    (li) => li.textContent,
  );
  expect(listed).toEqual(['Jan: 20', 'Feb: 60', 'Mar: 40']);
  expect(container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
  act(() => root.unmount());
});

test('the ends of the range are visible under the curve', async () => {
  const { container, root } = await mount(
    <MetricsTrend data={{ title: 'T', metrics: METRICS, series: SERIES }} />,
  );
  const ends = [...container.querySelectorAll('.genui-metrics__ends span')].map(
    (s) => s.textContent,
  );
  expect(ends).toEqual(['Jan', 'Mar']);
  act(() => root.unmount());
});

test('the highest point sits above the lowest, in path coordinates', async () => {
  const { container, root } = await mount(
    <MetricsTrend data={{ title: 'T', metrics: METRICS, series: SERIES }} />,
  );
  const line = container.querySelector('.genui-metrics__line')!.getAttribute('d')!;
  const ys = [...line.matchAll(/[\d.]+ ([\d.]+)/g)].map((m) => Number(m[1]));
  expect(Math.min(...ys)).toBe(ys[1]);
  expect(ys[0]).toBeGreaterThan(ys[2]);
  act(() => root.unmount());
});

test('a value that is not a number draws no curve, and the grid stays', async () => {
  const { container, root } = await mount(
    <MetricsTrend
      data={{
        title: 'T',
        metrics: METRICS,
        series: [{ label: 'Jan', value: 20 }, { label: 'Feb', value: Number.NaN }],
      }}
    />,
  );
  expect(container.querySelector('.genui-metrics__trend')).toBeNull();
  expect(container.querySelectorAll('.genui-metrics__item').length).toBe(2);
  act(() => root.unmount());
});

test('the tail is part of the title sentence, and optional', async () => {
  const withTail = await mount(
    <MetricsTrend data={{ title: 'Where we are,', tail: 'and how we got here.', metrics: METRICS, series: [] }} />,
  );
  expect(withTail.container.querySelector('h2')?.textContent).toBe(
    'Where we are, and how we got here.',
  );
  act(() => withTail.root.unmount());

  const without = await mount(
    <MetricsTrend data={{ title: 'Where we are', metrics: METRICS, series: [] }} />,
  );
  expect(without.container.querySelector('.genui-metrics__tail')).toBeNull();
  act(() => without.root.unmount());
});

test('two gradients on one page do not share an id', async () => {
  const { container, root } = await mount(
    <>
      <MetricsTrend data={{ title: 'A', metrics: METRICS, series: SERIES }} />
      <MetricsTrend data={{ title: 'B', metrics: METRICS, series: SERIES }} />
    </>,
  );
  const ids = [...container.querySelectorAll('linearGradient')].map((g) => g.id);
  expect(new Set(ids).size).toBe(2);
  expect(ids.every((id) => !id.includes(':'))).toBe(true);
  act(() => root.unmount());
});
