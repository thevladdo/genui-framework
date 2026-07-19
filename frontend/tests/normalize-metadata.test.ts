/**
 * Opaque metadata contract: BentoCard.metadata is a declared pass-through
 * (Dict[str, Any] on the backend) — its keys belong to the host, not to
 * the wire format, so normalizeData must not camelize them. Sibling keys
 * keep the snake_case -> camelCase normalization. Imports the TS source
 * directly (normalizeData is internal, not part of the public API).
 */

import { test, expect } from 'vitest';
import { normalizeData } from '../src/components/ComponentRenderer';

test('card metadata keys stay verbatim while siblings are camelized', () => {
  const out = normalizeData({
    cards: [
      {
        title: 'x',
        show_arrow: true,
        metadata: { external_id: 'abc', nested: { keep_me: 1 } },
      },
    ],
  });

  expect(out.cards[0].showArrow).toBe(true);
  expect(out.cards[0].metadata).toEqual({
    external_id: 'abc',
    nested: { keep_me: 1 },
  });
});
