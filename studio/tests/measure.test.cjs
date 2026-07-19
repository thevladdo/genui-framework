/**
 * Tests for the measurement dashboard's pure logic (lib/measure.ts).
 *
 * The point of this suite is honesty: the dashboard must never present
 * "significant" when the sample cannot back it, never show uplift with a
 * single arm, and never print fake precision.
 *
 * Run with `npm test` (compiles measure.ts to tests/.build first: local
 * node has no type stripping).
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  formatCount,
  formatCtr,
  formatUplift,
  formatPValue,
  verdict,
} = require("./.build/measure.js");

// Formatters
test("formatCtr renders fractions as one-decimal percentages", () => {
  assert.equal(formatCtr(0.0523), "5.2%");
  assert.equal(formatCtr(0), "0.0%");
  assert.equal(formatCtr(null), "–");
  assert.equal(formatCtr(undefined), "–");
});

test("formatUplift keeps the sign explicit", () => {
  assert.equal(formatUplift(12.37), "+12.4%");
  assert.equal(formatUplift(-3.1), "-3.1%");
  assert.equal(formatUplift(0), "0.0%");
  assert.equal(formatUplift(null), "–");
});

test("formatPValue refuses fake precision below 0.001", () => {
  assert.equal(formatPValue(0.032), "p = 0.032");
  assert.equal(formatPValue(0.0009), "p < 0.001");
  assert.equal(formatPValue(0), "p < 0.001");
});

test("formatCount separates thousands and tolerates missing values", () => {
  assert.equal(formatCount(12345), "12,345");
  assert.equal(formatCount(0), "0");
  assert.equal(formatCount(undefined), "–");
});

// Verdict: the honesty ladder
const base = (overrides) => ({
  zone_id: "z",
  arms: {},
  uplift_percent: null,
  significance: null,
  holdout_percent: 10,
  ...overrides,
});

test("no arms at all = no data", () => {
  const v = verdict(base({}));
  assert.equal(v.tone, "muted");
  assert.match(v.label, /No data/i);
});

test("arms present but zero impressions = still no data", () => {
  const v = verdict(
    base({ arms: { personalized: { click: 3, ctr: null } } }),
  );
  assert.equal(v.tone, "muted");
  assert.match(v.label, /No data/i);
});

test("a single arm cannot claim uplift", () => {
  const v = verdict(
    base({ arms: { personalized: { impression: 500, click: 30, ctr: 0.06 } } }),
  );
  assert.equal(v.tone, "neutral");
  assert.match(v.label, /not measurable/i);
  assert.match(v.detail, /10%/, "mentions the holdout share");
});

test("both arms but no computable test = not testable", () => {
  const v = verdict(
    base({
      arms: {
        personalized: { impression: 50, click: 0, ctr: 0 },
        control: { impression: 50, click: 0, ctr: 0 },
      },
      significance: null,
    }),
  );
  assert.equal(v.tone, "muted");
  assert.match(v.label, /Not testable/i);
});

test("sample_warning beats significant_95: never green under the threshold", () => {
  const v = verdict(
    base({
      arms: {
        personalized: { impression: 40, click: 12, ctr: 0.3 },
        control: { impression: 45, click: 2, ctr: 0.044 },
      },
      uplift_percent: 575.0,
      significance: {
        method: "two-proportion z-test (two-tailed)",
        z_score: 3.1,
        p_value: 0.002,
        significant_95: true,
        sample_warning: true,
      },
    }),
  );
  assert.equal(v.tone, "warning");
  assert.match(v.label, /Preliminary/i);
  assert.doesNotMatch(v.label, /significant/i);
});

test("significant with a solid sample is the only green", () => {
  const v = verdict(
    base({
      arms: {
        personalized: { impression: 5000, click: 400, ctr: 0.08 },
        control: { impression: 500, click: 25, ctr: 0.05 },
      },
      uplift_percent: 60.0,
      significance: {
        method: "two-proportion z-test (two-tailed)",
        z_score: 2.4,
        p_value: 0.016,
        significant_95: true,
        sample_warning: false,
      },
    }),
  );
  assert.equal(v.tone, "success");
  assert.match(v.detail, /p = 0\.016/);
});

test("solid sample but p >= 0.05 = honest 'no difference yet'", () => {
  const v = verdict(
    base({
      arms: {
        personalized: { impression: 2000, click: 100, ctr: 0.05 },
        control: { impression: 400, click: 19, ctr: 0.0475 },
      },
      uplift_percent: 5.3,
      significance: {
        method: "two-proportion z-test (two-tailed)",
        z_score: 0.2,
        p_value: 0.84,
        significant_95: false,
        sample_warning: false,
      },
    }),
  );
  assert.equal(v.tone, "neutral");
  assert.match(v.label, /No significant difference/i);
});
