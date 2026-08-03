/**
 * The bento has to fill the space it is given, whatever the card count.
 */

import { test, expect } from "vitest";
import {
  bentoSpans,
  bentoSpanClass,
  featuredFirst,
} from "../src/utils/bentoLayout";

const pack = (spans: ReturnType<typeof bentoSpans>): number[] => {
  const rows: number[] = [];
  const occupied: number[] = [];
  let row = 0;
  for (const span of spans) {
    while ((rows[row] ?? 0) + (occupied[row] ?? 0) + span.w > 12) row += 1;
    rows[row] = (rows[row] ?? 0) + span.w;
    for (let extra = 1; extra < (span.h ?? 1); extra += 1) {
      occupied[row + extra] = (occupied[row + extra] ?? 0) + span.w;
    }
  }
  return rows.map((width, i) => width + (occupied[i] ?? 0));
};

test("every arrangement fills every row it opens", () => {
  for (let columns = 2; columns <= 4; columns += 1) {
    for (let count = columns; count <= 14; count += 1) {
      const spans = bentoSpans(count, columns);
      expect(spans).toHaveLength(count);
      for (const row of pack(spans)) {
        expect(row, `count=${count} columns=${columns}`).toBe(12);
      }
    }
  }
});

test("a single card takes the whole width", () => {
  expect(bentoSpans(1, 3)).toEqual([{ w: 12 }]);
});

test("the card left alone on the last row widens instead of staying thin", () => {
  expect(bentoSpans(7, 3).slice(-1)).toEqual([{ w: 12 }]);
  expect(bentoSpans(9, 4).slice(-1)).toEqual([{ w: 12 }]);
});

test("two left over split the last row in half", () => {
  expect(bentoSpans(8, 3).slice(-2)).toEqual([{ w: 6 }, { w: 6 }]);
});

test("the cells are never all equal: one card leads", () => {
  for (const count of [3, 5, 6, 7, 9, 12]) {
    const spans = bentoSpans(count, 3);
    expect(spans[0], `count=${count}`).toEqual({ w: 8, h: 2 });
    expect(
      new Set(spans.map((s) => s.w)).size,
      `count=${count}`,
    ).toBeGreaterThan(1);
  }
  expect(bentoSpans(4, 3)).toEqual([{ w: 8 }, { w: 4 }, { w: 4 }, { w: 8 }]);
  expect(bentoSpans(2, 3)).toEqual([{ w: 8 }, { w: 4 }]);
});

test("an explicit four-across density stays an even grid", () => {
  expect(bentoSpans(8, 4)).toEqual(Array.from({ length: 8 }, () => ({ w: 3 })));
});

test("the featured card leads, whatever its position", () => {
  const cards = [
    { title: "A" },
    { title: "B", featured: true },
    { title: "C" },
  ];
  expect(featuredFirst(cards as never).map((c) => c.title)).toEqual([
    "B",
    "A",
    "C",
  ]);
});

test("two featured cards are no featured card: the first claim wins", () => {
  const cards = [
    { title: "A" },
    { title: "B", featured: true },
    { title: "C", featured: true },
  ];
  expect(featuredFirst(cards as never).map((c) => c.title)).toEqual([
    "B",
    "A",
    "C",
  ]);
});

test("nothing moves when the leading card is already first", () => {
  const cards = [{ title: "A", featured: true }, { title: "B" }];
  expect(featuredFirst(cards as never).map((c) => c.title)).toEqual(["A", "B"]);
});

test("the span becomes the classes the stylesheet knows", () => {
  expect(bentoSpanClass({ w: 8, h: 2 })).toBe(
    "genui-bento-card--w8 genui-bento-card--h2",
  );
  expect(bentoSpanClass({ w: 4 })).toBe("genui-bento-card--w4");
});
