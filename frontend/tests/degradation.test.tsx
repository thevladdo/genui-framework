// @vitest-environment jsdom
/**
 * Degradation contract: every component renders a deliberate layout for
 * whatever subset of optional data it gets — no empty shells, no
 * padding, no meaningless chrome. These tests pin the cases where a
 * missing field must change the markup, not just leave a hole.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { HeroBanner, PricingCards, QuoteBlock, TabsFeature } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

test('hero with no usable CTA renders no cta row at all', async () => {
  const { container, root } = await mount(
    <HeroBanner data={{ variant: 'minimal', headline: 'H' }} />,
  );
  expect(container.querySelector('.genui-hero__ctas')).toBeNull();
  act(() => root.unmount());
});

test('hero with one CTA renders exactly one button', async () => {
  const { container, root } = await mount(
    <HeroBanner
      data={{ variant: 'minimal', headline: 'H', primaryCta: { label: 'Go', url: '/go' } }}
    />,
  );
  expect(container.querySelectorAll('.genui-hero__cta').length).toBe(1);
  act(() => root.unmount());
});

test('plan without features renders no empty feature list', async () => {
  const { container, root } = await mount(
    <PricingCards data={{ plans: [{ name: 'Solo', price: '$9', features: [] }] }} />,
  );
  expect(container.querySelector('.genui-pricing__features')).toBeNull();
  act(() => root.unmount());
});

test('detailed variant with a single plan degrades to plain cards (no table)', async () => {
  const { container, root } = await mount(
    <PricingCards
      data={{
        variant: 'detailed',
        plans: [{ name: 'Solo', price: '$9', features: ['A', 'B'] }],
      }}
    />,
  );
  expect(container.querySelector('.genui-pricing__table')).toBeNull();
  act(() => root.unmount());
});

test('detailed variant with two plans keeps the comparison table', async () => {
  const { container, root } = await mount(
    <PricingCards
      data={{
        variant: 'detailed',
        plans: [
          { name: 'Solo', price: '$9', features: ['A'] },
          { name: 'Team', price: '$29', features: ['A', 'B'] },
        ],
      }}
    />,
  );
  expect(container.querySelector('.genui-pricing__table')).not.toBeNull();
  act(() => root.unmount());
});

test('quote avatar without an author is not rendered (anonymous face)', async () => {
  const { container, root } = await mount(
    <QuoteBlock data={{ quote: 'Q', avatarUrl: '/face.jpg' }} />,
  );
  expect(container.querySelector('.genui-quote__avatar')).toBeNull();
  expect(container.querySelector('.genui-quote__attribution')).toBeNull();
  act(() => root.unmount());
});

test('single tab renders the panel without a tab bar', async () => {
  const { container, root } = await mount(
    <TabsFeature
      data={{
        heading: 'One thing',
        tabs: [{ label: 'Only', content: { layout: 'text-only', title: 'T' } }],
      }}
    />,
  );
  expect(container.querySelector('[role="tablist"]')).toBeNull();
  expect(container.querySelector('[role="tabpanel"]')).not.toBeNull();
  act(() => root.unmount());
});
