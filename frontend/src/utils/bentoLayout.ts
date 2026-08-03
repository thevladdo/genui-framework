/**
 * What each bento card spans, on a twelve column grid.
 *
 * A bento is not a grid of equal boxes and fills the space it is given whatever the number of cards.
 */

import type { BentoCard } from "../types";

export interface BentoSpan {
  /** Columns out of twelve */
  w: number;
  /** Rows, when the card leads */
  h?: number;
}

const evenGrid = (
  count: number,
  base: number,
  columns: number,
): BentoSpan[] => {
  const leftover = count % columns;
  const spans: BentoSpan[] = Array.from({ length: count - leftover }, () => ({
    w: base,
  }));
  for (let i = 0; i < leftover; i += 1)
    spans.push({ w: Math.floor(12 / leftover) });
  return spans;
};

export const bentoSpans = (count: number, columns: number): BentoSpan[] => {
  if (count <= 0) return [];
  if (count === 1) return [{ w: 12 }];
  if (columns >= 4) return evenGrid(count, 3, 4);
  if (count === 2) return [{ w: 8 }, { w: 4 }];
  if (count === 4) return [{ w: 8 }, { w: 4 }, { w: 4 }, { w: 8 }];

  const spans: BentoSpan[] = [{ w: 8, h: 2 }, { w: 4 }, { w: 4 }];
  let rest = count - 3;
  while (rest >= 3) {
    spans.push({ w: 4 }, { w: 4 }, { w: 4 });
    rest -= 3;
  }
  if (rest === 1) spans.push({ w: 12 });
  if (rest === 2) spans.push({ w: 6 }, { w: 6 });
  return spans;
};

/**
 * The card that leads goes first. Grid placement follows the DOM.
 */
export const featuredFirst = (cards: BentoCard[]): BentoCard[] => {
  const lead = cards.findIndex((card) => card?.featured);
  if (lead <= 0) return cards;
  return [cards[lead], ...cards.filter((_, i) => i !== lead)];
};

export const bentoSpanClass = (span: BentoSpan): string =>
  `genui-bento-card--w${span.w}${span.h ? ` genui-bento-card--h${span.h}` : ""}`;
