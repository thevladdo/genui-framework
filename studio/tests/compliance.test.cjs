/**
 * Guards on the public compliance page.
 *
 * Two things can rot here without anyone noticing, and both are public:
 * a link to a document that has been renamed or removed, and a sentence
 * that quietly turns "here is the mechanism" into "you are compliant".
 *
 * Run with `npm test`.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const REPO = path.resolve(__dirname, "..", "..");
const SOURCE = fs.readFileSync(
  path.join(REPO, "studio", "src", "components", "compliance", "Compliance.tsx"),
  "utf8",
);

const linkedDocs = [...SOURCE.matchAll(/file: '([A-Z0-9-]+\.md)'/g)].map((m) => m[1]);

test("every document the page links to exists in deploy/", () => {
  assert.ok(linkedDocs.length >= 4, `expected the four deploy documents, got ${linkedDocs.length}`);
  for (const doc of linkedDocs) {
    assert.ok(
      fs.existsSync(path.join(REPO, "deploy", doc)),
      `${doc} is linked from the compliance page but is not in deploy/`,
    );
  }
});

test("the documents are linked under deploy/ on the default branch", () => {
  const base = SOURCE.match(/DOC_BASE = '([^']+)'/);
  assert.ok(base, "DOC_BASE is gone: the document links no longer resolve");
  assert.equal(base[1], "https://github.com/thevladdo/genui-framework/blob/main/deploy/");
});

test("the page claims no conformity", () => {
  const prose = SOURCE.toLowerCase();

  for (const claim of ["guarantees compliance", "ensures compliance", "certified"]) {
    assert.ok(!prose.includes(claim), `the page states "${claim}"`);
  }

  // "compliant" is allowed only where the page denies the claim, as the
  // disclaimer does. An affirmative one is the sentence this page exists
  // to never contain.
  for (const match of prose.matchAll(/compliant/g)) {
    const head = prose.slice(0, match.index);
    const sentence = head.slice(head.lastIndexOf(".") + 1);
    assert.match(
      sentence,
      /\b(nothing|not|never|no)\b/,
      `"compliant" is used affirmatively in: ${sentence.trim()} compliant`,
    );
  }
});

test("the disclaimer is on the page", () => {
  assert.ok(
    SOURCE.includes("engineering documentation, not legal advice"),
    "the disclaimer has been removed from the compliance page",
  );
});
