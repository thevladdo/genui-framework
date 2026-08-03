// @vitest-environment jsdom
/**
 * pros_cons: the shapes, and the markdown path.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ProsCons } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

test('both sides render two columns with their own headings', async () => {
  const { container, root } = await mount(
    <ProsCons data={{ title: 'Serverless', pros: ['Cheap'], cons: ['Cold starts'] }} />,
  );
  expect(container.querySelectorAll('.genui-proscons__col').length).toBe(2);
  expect(container.querySelector('.genui-proscons__cols--single')).toBeNull();
  expect(container.querySelector('.genui-proscons__title')?.textContent).toBe('Serverless');
  act(() => root.unmount());
});

test('one populated side is one full-width column, not half a grid', async () => {
  const { container, root } = await mount(
    <ProsCons data={{ pros: ['Cheap', 'Fast'], cons: [] }} />,
  );
  expect(container.querySelectorAll('.genui-proscons__col').length).toBe(1);
  expect(container.querySelector('.genui-proscons__cols--single')).not.toBeNull();
  expect(container.querySelector('.genui-proscons__col--con')).toBeNull();
  act(() => root.unmount());
});

test('blank entries never become empty bullets', async () => {
  const { container, root } = await mount(
    <ProsCons data={{ pros: ['Cheap'], cons: ['   ', ''] }} />,
  );
  expect(container.querySelectorAll('.genui-proscons__item').length).toBe(1);
  expect(container.querySelector('.genui-proscons__col--con')).toBeNull();
  act(() => root.unmount());
});

test('nothing on either side renders nothing at all', async () => {
  const { container, root } = await mount(<ProsCons data={{ pros: [], cons: [] }} />);
  expect(container.querySelector('.genui-proscons')).toBeNull();
  act(() => root.unmount());
});

test('no title renders no heading element', async () => {
  const { container, root } = await mount(
    <ProsCons data={{ pros: ['A'], cons: ['B'] }} />,
  );
  expect(container.querySelector('.genui-proscons__title')).toBeNull();
  expect(container.querySelectorAll('.genui-proscons__col').length).toBe(2);
  act(() => root.unmount());
});

test('tone is not carried by color alone: heading text plus icon shape', async () => {
  const { container, root } = await mount(
    <ProsCons data={{ prosHeading: 'Vantaggi', consHeading: 'Limiti', pros: ['A'], cons: ['B'] }} />,
  );
  const heads = [...container.querySelectorAll('.genui-proscons__head')].map(
    (h) => h.textContent,
  );
  expect(heads).toEqual(['Vantaggi', 'Limiti']);
  // Each list item carries its own mark, so the row reads without the header
  expect(container.querySelectorAll('.genui-proscons__item svg').length).toBe(2);
  act(() => root.unmount());
});

test('items are a real list, headings are real headings', async () => {
  const { container, root } = await mount(
    <ProsCons data={{ title: 'T', pros: ['A', 'B'], cons: ['C'] }} />,
  );
  expect(container.querySelector('h2')?.textContent).toBe('T');
  expect(container.querySelectorAll('h3').length).toBe(2);
  expect(container.querySelectorAll('ul > li').length).toBe(3);
  act(() => root.unmount());
});

test('item markdown renders, and a dangerous link is neutralized', async () => {
  const { container, root } = await mount(
    <ProsCons
      data={{
        pros: ['**Bold** and [safe](https://acme.example/docs)'],
        cons: ['[tap here](javascript:alert(1))'],
      }}
    />,
  );
  expect(container.querySelector('.genui-proscons__text strong')?.textContent).toBe('Bold');
  const hrefs = [...container.querySelectorAll('a')].map((a) => a.getAttribute('href'));
  expect(hrefs).toContain('https://acme.example/docs');
  expect(hrefs.some((h) => (h ?? '').startsWith('javascript:'))).toBe(false);
  act(() => root.unmount());
});
