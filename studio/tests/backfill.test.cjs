/**
 * The console walks a backfill in runs (lib/api.ts backfillInRuns): it
 * calls again while work is left, and never after the run was stopped.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const stored = new Map();
globalThis.sessionStorage = {
  getItem: (key) => (stored.has(key) ? stored.get(key) : null),
  setItem: (key, value) => stored.set(key, String(value)),
  removeItem: (key) => stored.delete(key),
};

const { saveSession } = require("./.build/session.js");
const { backfillInRuns } = require("./.build/api.js");

const ACME = { baseUrl: "http://localhost:8000", adminKey: "sk_a", tenant: "acme" };
saveSession(ACME);

const serve = (reports) => {
  const bodies = [];
  globalThis.fetch = async (url, init) => {
    bodies.push(JSON.parse(init.body));
    if (bodies.length > reports.length + 1) {
      throw new Error(`backfill called ${bodies.length} times for ${reports.length} reports`);
    }
    const report = reports[Math.min(bodies.length - 1, reports.length - 1)];
    return { ok: true, status: 200, json: async () => report };
  };
  return bodies;
};

const partial = (done, remaining) => ({
  status: "partial", chunks_plain: remaining, context_calls: 0,
  chunks_contextualized: done, chunks_plain_remaining: remaining,
});

test("it carries on while work is left, under one run id", async () => {
  const bodies = serve([
    partial(500, 700),
    partial(500, 200),
    { ...partial(200, 0), status: "completed" },
  ]);
  const seen = [];
  const report = await backfillInRuns(ACME, "run-1", (left) => seen.push(left));

  assert.equal(report.status, "completed");
  assert.equal(bodies.length, 3);
  assert.ok(bodies.every((body) => body.ingest_id === "run-1"));
  assert.deepEqual(seen, [700, 200, 0]);
});

test("a stopped run is not called again", async () => {
  const bodies = serve([
    partial(500, 700),
    { ...partial(120, 580), status: "cancelled" },
    partial(500, 80),
  ]);
  const report = await backfillInRuns(ACME, "run-2", () => {});

  assert.equal(report.status, "cancelled");
  assert.equal(bodies.length, 2);
});

test("a run that moved nothing ends the loop", async () => {
  const bodies = serve([partial(0, 700), partial(500, 200)]);
  await backfillInRuns(ACME, "run-3", () => {});

  assert.equal(bodies.length, 1);
});
