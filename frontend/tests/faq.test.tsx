// @vitest-environment jsdom
/**
 * FAQ.
 *
 * The open and close behaviour comes from details and summary, so what
 * is worth testing is that it really is those elements, that the content
 * exists in server rendered HTML before any script runs.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { Faq } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const ITEMS = [
  { question: 'What is included?', answer: 'Everything in the plan.' },
  { question: 'How do I cancel?', answer: 'From the **billing** page.' },
];

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

test('the accordion is details and summary, not a rebuilt one', async () => {
  const { container, root } = await mount(
    <Faq data={{ title: 'Common questions', items: ITEMS }} />,
  );
  const items = container.querySelectorAll('details.genui-faq__item');
  expect(items.length).toBe(2);
  expect(items[0].querySelector('summary')).not.toBeNull();
  const names = [...items].map((d) => d.getAttribute('name'));
  expect(new Set(names).size).toBe(1);
  expect(names[0]).toBeTruthy();
  act(() => root.unmount());
});

test('the content is in the server rendered HTML, before any script runs', () => {
  const html = renderToString(
    React.createElement(Faq, {
      data: { title: 'Common questions', intro: 'Answers to what people ask.', items: ITEMS },
    }),
  );
  expect(html).toContain('Common questions');
  expect(html).toContain('What is included?');
  expect(html).toContain('Everything in the plan.');
  expect(html).toContain('How do I cancel?');
  expect(html).toContain('<details');
  expect(html).toContain('<summary');
});

test('no structured data is emitted beside the zone declaration', () => {
  const html = renderToString(
    React.createElement(Faq, { data: { title: 'T', items: ITEMS } }),
  );
  expect(html).not.toContain('application/ld+json');
  expect(html).not.toContain('FAQPage');
  expect(html).not.toContain('schema.org');
});

test('answers render markdown, and a dangerous link is neutralized', async () => {
  const { container, root } = await mount(
    <Faq
      data={{
        title: 'T',
        items: [
          { question: 'Q1', answer: 'Read the [docs](https://acme.example/docs).' },
          { question: 'Q2', answer: 'Tap [here](javascript:alert(1)).' },
        ],
      }}
    />,
  );
  const hrefs = [...container.querySelectorAll('a')].map((a) => a.getAttribute('href'));
  expect(hrefs).toContain('https://acme.example/docs');
  expect(hrefs.some((h) => (h ?? '').startsWith('javascript:'))).toBe(false);
  act(() => root.unmount());
});

test('no intro renders no paragraph, and entries without content are skipped', async () => {
  const { container, root } = await mount(
    <Faq
      data={{
        title: 'T',
        items: [...ITEMS, { question: '', answer: 'orphan' } as never],
      }}
    />,
  );
  expect(container.querySelector('.genui-faq__intro')).toBeNull();
  expect(container.querySelectorAll('details').length).toBe(2);
  act(() => root.unmount());
});

test('nothing usable renders nothing', async () => {
  const { container, root } = await mount(<Faq data={{ title: 'T', items: [] }} />);
  expect(container.querySelector('.genui-faq')).toBeNull();
  act(() => root.unmount());
});
