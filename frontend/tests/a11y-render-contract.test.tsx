// @vitest-environment jsdom
/**
 * The state a component announces is the state it has: a disabled link cannot be followed, the selected tab exists, and the light text-only CTA is not accent on accent.
 */

import { test, expect } from 'vitest';
import React, { act } from 'react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createRoot } from 'react-dom/client';
import { ButtonsComponent, TabsFeature } from 'genui-framework';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mount = async (node: React.ReactElement) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(node);
  });
  return { container, root };
};

test('a disabled link is not an activatable anchor and keeps its label', async () => {
  const { container, root } = await mount(
    <ButtonsComponent
      data={{ buttons: [{ label: 'Download', url: 'https://ex.com/file', disabled: true }] }}
    />,
  );
  expect(container.querySelector('a[href]')).toBeNull();
  const button = container.querySelector('button')!;
  expect(button.disabled).toBe(true);
  expect(button.textContent).toContain('Download');
  act(() => root.unmount());
});

test('an enabled link is still an anchor', async () => {
  const { container, root } = await mount(
    <ButtonsComponent data={{ buttons: [{ label: 'Open', url: 'https://ex.com/' }] }} />,
  );
  expect(container.querySelector('a[href]')?.getAttribute('href')).toBe('https://ex.com/');
  act(() => root.unmount());
});

const tabs = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    label: `Tab ${i}`,
    content: { layout: 'text-only' as const, title: `Panel ${i}` },
  }));

test('when the tab list shrinks, the selected tab is one that exists', async () => {
  const { container, root } = await mount(<TabsFeature data={{ heading: 'H', tabs: tabs(3) }} />);
  const third = container.querySelectorAll<HTMLButtonElement>('[role="tab"]')[2];
  await act(async () => {
    third.click();
  });

  await act(async () => {
    root.render(<TabsFeature data={{ heading: 'H', tabs: tabs(2) }} />);
  });

  const rendered = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
  const selected = rendered.filter((t) => t.getAttribute('aria-selected') === 'true');
  expect(selected).toHaveLength(1);
  expect(selected[0].tabIndex).toBe(0);
  expect(rendered.filter((t) => t.tabIndex === 0)).toHaveLength(1);
  const panel = container.querySelector('[role="tabpanel"]')!;
  expect(panel.getAttribute('aria-labelledby')).toBe(selected[0].id);
  expect(panel.textContent).toContain(selected[0].textContent!.replace('Tab', 'Panel'));
  act(() => root.unmount());
});

test('a single tab renders its content without pointing at a tab that does not exist', async () => {
  const { container, root } = await mount(<TabsFeature data={{ heading: 'H', tabs: tabs(1) }} />);
  expect(container.querySelector('[role="tablist"]')).toBeNull();
  expect(container.querySelector('[role="tabpanel"]')).toBeNull();
  for (const el of Array.from(container.querySelectorAll('[aria-labelledby]'))) {
    expect(document.getElementById(el.getAttribute('aria-labelledby')!)).not.toBeNull();
  }
  expect(container.textContent).toContain('Panel 0');
  act(() => root.unmount());
});

test('the light text-only bento CTA uses the on-accent text token', () => {
  const css = readFileSync(join(__dirname, '../src/styles/genui.css'), 'utf8');
  const rule = css.match(
    /\[data-theme='light'\] \.genui-bento-card--text-only \.genui-bento-card__action \{([^}]*)\}/,
  );
  expect(rule).not.toBeNull();
  expect(rule![1]).toMatch(/color:\s*var\(--genui-text-on-accent\)/);
  expect(rule![1]).not.toMatch(/accent-color/);
});
