/**
 * SSR contract: renderToString of a zone that will fetch on mount must
 * emit the loading skeleton (stable HTML, no CLS, honest with the README)
 * instead of empty markup. Runs against the BUILT package, in plain node
 * (react-dom/server needs no DOM).
 */

import { test, expect } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { GenUIZone } from 'genui-framework';

test('renderToString emits the loading skeleton, not empty HTML', () => {
  const html = renderToString(
    React.createElement(GenUIZone, { apiUrl: 'http://backend.test', zoneId: 'ssr-zone' })
  );
  expect(html).toContain('genui-zone-skeleton');
  expect(html).toContain('genui-zone--loading');
});

test('loadOnMount=false renders nothing on the server (nothing will load)', () => {
  const html = renderToString(
    React.createElement(GenUIZone, {
      apiUrl: 'http://backend.test',
      zoneId: 'ssr-zone',
      loadOnMount: false,
    })
  );
  expect(html).toBe('');
});
