// @vitest-environment jsdom
/**
 * A host registration wins over the framework's own component of the same name.
 *
 * An override of a built-in stands in for the component it replaces, so it gets 
 * the same camelCase data. A custom type is validated against the host's own 
 * JSON Schema, so it gets the keys that schema declared, untouched.
 */

import { test, expect, afterEach } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ComponentRenderer, registerGenUIComponent, BUILTIN_TYPES } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const cleanups: Array<() => void> = [];
afterEach(() => {
  while (cleanups.length) cleanups.pop()!();
});

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

test('a registration replaces the built-in component of the same name', async () => {
  cleanups.push(
    registerGenUIComponent('hero_banner', ({ data }) => (
      <div className="acme-hero">{(data as any).headline}</div>
    )),
  );

  const { container, root } = await mount(
    <ComponentRenderer
      component={{
        type: 'hero_banner',
        data: { variant: 'centered', headline: 'Acme owns this markup' },
      } as any}
    />,
  );

  expect(container.querySelector('.acme-hero')?.textContent).toBe('Acme owns this markup');
  expect(container.querySelector('.genui-herobanner')).toBeNull();
  await act(async () => root.unmount());
});

test('an override of a built-in receives camelCase data, like the component it replaces', async () => {
  let seen: any = null;
  cleanups.push(
    registerGenUIComponent('hero_banner', ({ data }) => {
      seen = data;
      return <div className="acme-hero" />;
    }),
  );

  const { root } = await mount(
    <ComponentRenderer
      component={{
        type: 'hero_banner',
        data: { headline: 'x', primary_cta: { label: 'Go', url: '/go' } },
      } as any}
    />,
  );

  expect(seen.primaryCta).toEqual({ label: 'Go', url: '/go' });
  expect(seen.primary_cta).toBeUndefined();
  await act(async () => root.unmount());
});

test('a custom type receives the keys its own schema declared', async () => {
  let seen: any = null;
  cleanups.push(
    registerGenUIComponent('acme_offer_card', ({ data }) => {
      seen = data;
      return <div className="acme-offer" />;
    }),
  );

  const { root } = await mount(
    <ComponentRenderer
      component={{
        type: 'acme_offer_card',
        data: { title: 'Home cover', cta_url: '/quotes/home' },
      } as any}
    />,
  );

  expect(seen.cta_url).toBe('/quotes/home');
  expect(seen.ctaUrl).toBeUndefined();
  await act(async () => root.unmount());
});

test('every type the renderer draws is listed as built-in', () => {
  // The list drives the camelCase decision above. If a new section component
  // is added to the renderer and not to the list, its overrides would start
  // receiving snake_case and break with no error.
  for (const name of ['bento', 'chart', 'text', 'buttons', 'hero_banner', 'logo_wall']) {
    expect(BUILTIN_TYPES).toContain(name);
  }
  expect(BUILTIN_TYPES).toHaveLength(18);
});
