/**
 * The console knows the upload limit before it sends anything (lib/api.ts):
 * a file over it is refused on the spot, a file at it goes through, and with
 * no limit reported the backend is the one that decides.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const { tooLarge } = require("./.build/api.js");

const MB = 1024 * 1024;
const corpus = (limit) => ({ max_upload_bytes: limit });

test("a file over the limit is refused, one at the limit is not", () => {
  assert.equal(tooLarge(50 * MB + 1, corpus(50 * MB)), true);
  assert.equal(tooLarge(50 * MB, corpus(50 * MB)), false);
});

test("without a reported limit the console sends and the backend decides", () => {
  assert.equal(tooLarge(500 * MB, null), false);
  assert.equal(tooLarge(500 * MB, {}), false);
});
