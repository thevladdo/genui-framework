// @vitest-environment jsdom
/**
 * Render + graceful-degradation coverage for the editorial components
 * (case_studies, quote, logo_wall): built for absent data, never inventing
 * an image, a figure, a name, or a link that was not provided.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { CaseStudies, QuoteBlock, LogoWall } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

// QuoteBlock

test('quote renders statement-only, no attribution when nothing is given', async () => {
  const { container, root } = await mount(
    <QuoteBlock data={{ quote: 'We sell the difference between before and after.' }} />,
  );
  expect(container.querySelector('.genui-quote__text')?.textContent).toContain('before and after');
  expect(container.querySelector('.genui-quote__attribution')).toBeNull();
  expect(container.querySelector('.genui-quote__logo')).toBeNull();
  act(() => root.unmount());
});

test('quote shows logo, author, role and avatar when provided', async () => {
  const { container, root } = await mount(
    <QuoteBlock
      data={{
        quote: 'Q',
        author: 'Giulia',
        role: 'Director',
        avatarUrl: '/a.jpg',
        logoUrl: '/logo.svg',
        logoLabel: 'Northwind',
      }}
    />,
  );
  expect(container.querySelector('.genui-quote__author')?.textContent).toBe('Giulia');
  expect(container.querySelector('.genui-quote__role')?.textContent).toBe('Director');
  expect(container.querySelector('.genui-quote__avatar')?.getAttribute('src')).toBe('/a.jpg');
  const logoImg = container.querySelector('.genui-quote__logo img');
  expect(logoImg?.getAttribute('src')).toBe('/logo.svg');
  // The label never doubles a logo image: it becomes the alt instead
  expect(container.querySelector('.genui-quote__logo-label')).toBeNull();
  expect(logoImg?.getAttribute('alt')).toBe('Northwind');
  act(() => root.unmount());
});

test('quote label alone renders as a text wordmark', async () => {
  const { container, root } = await mount(
    <QuoteBlock data={{ quote: 'Q', logoLabel: 'Northwind' }} />,
  );
  expect(container.querySelector('.genui-quote__logo-label')?.textContent).toBe('Northwind');
  expect(container.querySelector('.genui-quote__logo img')).toBeNull();
  act(() => root.unmount());
});

// LogoWall

test('logo wall drops logos with no image and centers the rest', async () => {
  const { container, root } = await mount(
    <LogoWall
      data={{
        logos: [
          { imageUrl: '/a.svg', alt: 'A' },
          { imageUrl: '', alt: 'no image' },
          { imageUrl: 'javascript:alert(1)', alt: 'unsafe' },
          { imageUrl: '/b.svg', alt: 'B' },
        ],
      }}
    />,
  );
  const logos = container.querySelectorAll('.genui-logowall__logo');
  expect(logos.length).toBe(2); // empty + unsafe dropped
  act(() => root.unmount());
});

test('logo wall hover reveal only when an overall cta link exists', async () => {
  const withCta = await mount(
    <LogoWall
      data={{
        heading: 'Selected clients',
        ctaLabel: 'All clients',
        ctaUrl: '/clients',
        logos: [{ imageUrl: '/a.svg', alt: 'A' }],
      }}
    />,
  );
  expect(withCta.container.querySelector('.genui-logowall--reveal')).not.toBeNull();
  expect(withCta.container.querySelector('.genui-logowall__cta')?.getAttribute('href')).toBe('/clients');
  act(() => withCta.root.unmount());

  const noCta = await mount(
    <LogoWall data={{ heading: 'Our stack', logos: [{ imageUrl: '/a.svg', alt: 'A' }] }} />,
  );
  expect(noCta.container.querySelector('.genui-logowall--reveal')).toBeNull();
  expect(noCta.container.querySelector('.genui-logowall__cta')).toBeNull();
  act(() => noCta.root.unmount());
});

// CaseStudies

test('case renders image + metrics; a text-first case omits the image', async () => {
  const { container, root } = await mount(
    <CaseStudies
      data={{
        cases: [
          {
            title: 'With image',
            imageUrl: '/x.jpg',
            metrics: [{ value: '40%', label: 'Faster' }],
          },
          { title: 'Text first' },
        ],
      }}
    />,
  );
  const cases = container.querySelectorAll('.genui-cases__case');
  expect(cases.length).toBe(2);
  expect(cases[0].querySelector('.genui-cases__media img')?.getAttribute('src')).toBe('/x.jpg');
  expect(cases[1].querySelector('.genui-cases__media')).toBeNull(); // degraded
  // Metric value is shown (static in jsdom: no IntersectionObserver)
  expect(cases[0].querySelector('.genui-cases__metric-value')?.textContent).toContain('40%');
  expect(cases[1].querySelector('.genui-cases__metrics')).toBeNull();
  act(() => root.unmount());
});

test('non-numeric metric value is shown verbatim, not animated', async () => {
  const { container, root } = await mount(
    <CaseStudies
      data={{ cases: [{ title: 'T', metrics: [{ value: 'Sold out', label: 'Status' }] }] }}
    />,
  );
  expect(container.querySelector('.genui-cases__metric-value')?.textContent).toBe('Sold out');
  act(() => root.unmount());
});
