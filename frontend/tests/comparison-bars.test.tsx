// @vitest-environment jsdom
/**
 * comparison_bars: the reading has to survive without the chart.
 *
 * Heights are relative to the tallest bar of the series (not to 100), 
 * every label and value stays in the DOM as text, and the highlight is carried by more than a color. 
 * The degraded forms are shapes of their own: no subtitle, no callout, no highlight at all, two bars only.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ComparisonBars } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

const heights = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('.genui-compare__item')).map((el) =>
    (el as HTMLElement).style.getPropertyValue('--genui-compare-height'),
  );

test('bar heights are relative to the tallest value, not to a hundred', async () => {
  const { container, root } = await mount(
    <ComparisonBars
      data={{
        title: 'Onboarding',
        bars: [
          { label: 'Us', value: 4, suffix: 'd', highlighted: true },
          { label: 'Them', value: 8, suffix: 'd' },
        ],
      }}
    />,
  );
  expect(heights(container)).toEqual(['50%', '100%']);
  act(() => root.unmount());
});

test('absolute values and percentages produce the same shape', async () => {
  const { container, root } = await mount(
    <ComparisonBars
      data={{
        title: 'Share',
        bars: [
          { label: 'A', value: 25, suffix: '%' },
          { label: 'B', value: 50, suffix: '%' },
        ],
      }}
    />,
  );
  expect(heights(container)).toEqual(['50%', '100%']);
  act(() => root.unmount());
});

test('label and value are readable as text, value formatted with its suffix', async () => {
  const { container, root } = await mount(
    <ComparisonBars
      data={{
        title: 'Requests',
        bars: [
          { label: 'Cached', value: 1200, suffix: '/s', highlighted: true },
          { label: 'Uncached', value: 240, suffix: '/s' },
        ],
      }}
    />,
  );
  const text = container.textContent ?? '';
  expect(text).toContain('Cached');
  expect(text).toContain('1,200/s');
  expect(text).toContain('240/s');
  act(() => root.unmount());
});

test('the highlight is not carried by color alone', async () => {
  const { container, root } = await mount(
    <ComparisonBars
      data={{
        title: 'Speed',
        bars: [
          { label: 'Us', value: 2, highlighted: true, callout: 'Twice as fast' },
          { label: 'Them', value: 4 },
        ],
      }}
    />,
  );
  const item = container.querySelector('.genui-compare__item--highlight');
  expect(item?.getAttribute('aria-current')).toBe('true');
  expect(container.querySelector('.genui-compare__callout')?.textContent).toBe(
    'Twice as fast',
  );
  act(() => root.unmount());
});

test('a highlighted bar without a callout still points at itself', async () => {
  const { container, root } = await mount(
    <ComparisonBars
      data={{
        title: 'Speed',
        bars: [
          { label: 'Us', value: 2, highlighted: true },
          { label: 'Them', value: 4 },
        ],
      }}
    />,
  );
  expect(container.querySelector('.genui-compare__callout')).toBeNull();
  expect(container.querySelector('.genui-compare__marker')).not.toBeNull();
  expect(container.querySelector('.genui-compare__chart--callout')).toBeNull();
  act(() => root.unmount());
});

test('no subtitle renders no header paragraph, no highlight renders no marker', async () => {
  const { container, root } = await mount(
    <ComparisonBars
      data={{
        title: 'Reading time',
        bars: [
          { label: 'Hero', value: 38, suffix: '%' },
          { label: 'Cards', value: 27, suffix: '%' },
        ],
      }}
    />,
  );
  expect(container.querySelector('.genui-compare__subtitle')).toBeNull();
  expect(container.querySelector('.genui-compare__item--highlight')).toBeNull();
  expect(container.querySelector('.genui-compare__marker')).toBeNull();
  act(() => root.unmount());
});

test('a zero next to real values keeps a visible sliver instead of vanishing', async () => {
  const { container, root } = await mount(
    <ComparisonBars
      data={{
        title: 'Incidents',
        bars: [
          { label: 'Us', value: 0, highlighted: true },
          { label: 'Them', value: 12 },
        ],
      }}
    />,
  );
  expect(heights(container)).toEqual(['2%', '100%']);
  act(() => root.unmount());
});

test('an unusable value renders nothing rather than a bar at a made-up height', async () => {
  const { container, root } = await mount(
    <ComparisonBars
      data={{
        title: 'Broken payload',
        bars: [
          { label: 'Us', value: 4 },
          { label: 'Them', value: Number.NaN },
        ],
      }}
    />,
  );
  expect(container.querySelector('.genui-compare')).toBeNull();
  act(() => root.unmount());
});
