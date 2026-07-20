/**
 * Tests for the segment preview's pure logic (lib/segment.ts).
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  slugify,
  segmentKey,
  buildRenderProfile,
  toSanitizationReport,
  sanitizationCount,
  isFallbackRender,
} = require("./.build/segment.js");

// segmentKey vs the pinned backend segmenter output

test("full archetype produces the backend key, factors in fixed order", () => {
  assert.equal(
    segmentKey({
      role: "Developer",
      interests: ["AI", "Sustainability"],
      userType: "deep_reader",
      engagement: "high",
    }),
    "role=developer|int=ai+sustainability|type=deep-reader|eng=high",
  );
});

test("no signals collapse into the anonymous segment", () => {
  assert.equal(segmentKey({}), "anon");
  assert.equal(
    segmentKey({ role: "", interests: [], userType: "", engagement: "" }),
    "anon",
  );
  // A role that slugifies to nothing is dropped, like the backend does.
  assert.equal(segmentKey({ role: "!!!" }), "anon");
});

test("interests are slugified, deduped, sorted, capped at 3", () => {
  assert.equal(
    segmentKey({ interests: ["Zebra", "beta", "Alpha", "gamma"] }),
    "int=alpha+beta+gamma",
  );
  assert.equal(segmentKey({ interests: ["ai", "AI!", "ai"] }), "int=ai");
});

test("empty-slug interests survive exactly like in the backend", () => {
  // Pinned: compute_segment({'!!!': ...}) -> "int=", with 'ai' -> "int=+ai"
  assert.equal(segmentKey({ interests: ["!!!"] }), "int=");
  assert.equal(segmentKey({ interests: ["!!!", "ai"] }), "int=+ai");
});

test("slugify matches the backend rules", () => {
  assert.equal(slugify("Data & AI Enthusiast!"), "data-ai-enthusiast");
  assert.equal(slugify("x".repeat(30)), "x".repeat(24));
  assert.equal(slugify("quick scanner"), "quick-scanner");
  assert.equal(segmentKey({ role: "Data & AI Enthusiast!" }), "role=data-ai-enthusiast");
});

test("partial signals keep their prefix, alone", () => {
  assert.equal(segmentKey({ engagement: "mid" }), "eng=mid");
  assert.equal(segmentKey({ userType: "quick scanner" }), "type=quick-scanner");
});

// buildRenderProfile: the request that lands in that segment

test("profile shape matches the API entry format the segmenter reads", () => {
  const { user_profile, behavior_data } = buildRenderProfile({
    role: "Developer",
    interests: ["AI", "Sustainability"],
    userType: "deep_reader",
    engagement: "high",
  });
  assert.deepEqual(user_profile, {
    preferences: { role: { value: "Developer", confidence: 1.0 } },
    interests: {
      AI: { value: true, confidence: 1.0 },
      Sustainability: { value: true, confidence: 1.0 },
    },
  });
  // Pinned: maxScrollDepth 90 buckets to eng=high (70/30 thresholds).
  assert.deepEqual(behavior_data, { userType: "deep_reader", maxScrollDepth: 90 });
});

test("engagement buckets use depths pinned against the backend thresholds", () => {
  assert.equal(buildRenderProfile({ engagement: "low" }).behavior_data.maxScrollDepth, 10);
  assert.equal(buildRenderProfile({ engagement: "mid" }).behavior_data.maxScrollDepth, 50);
  assert.equal(buildRenderProfile({ engagement: "high" }).behavior_data.maxScrollDepth, 90);
});

test("empty input produces a null profile, not empty objects", () => {
  assert.deepEqual(buildRenderProfile({}), {
    user_profile: null,
    behavior_data: null,
  });
});



test("toSanitizationReport maps snake_case and tolerates absence", () => {
  const report = toSanitizationReport({
    sanitization: {
      removed_urls: ["https://evil.example"],
      dropped_components: ["pricing_cards: incoherent layout"],
      removed_numbers: ["$499"],
      policy_violations: [],
    },
  });
  assert.deepEqual(report.removedUrls, ["https://evil.example"]);
  assert.deepEqual(report.droppedComponents, ["pricing_cards: incoherent layout"]);
  assert.deepEqual(report.removedNumbers, ["$499"]);
  assert.deepEqual(report.policyViolations, []);
  assert.equal(sanitizationCount(report), 3);

  const empty = toSanitizationReport(undefined);
  assert.equal(sanitizationCount(empty), 0);
});

test("isFallbackRender detects the ZoneAgent degradation sentinel", () => {
  assert.equal(
    isFallbackRender({
      reasoning:
        "Fallback render with only pinned content due to processing error",
    }),
    true,
  );
  assert.equal(isFallbackRender({ reasoning: "Curated for developers" }), false);
  assert.equal(isFallbackRender(undefined), false);
});
