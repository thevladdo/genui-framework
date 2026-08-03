/**
 * The brief handed to an outside AI assistant.
 */

const test = require("node:test");
const assert = require("node:assert");

const {
  AGENTS,
  MAX_PREFILL_CHARS,
  agentUrl,
  buildAgentPrompt,
  prefills,
} = require("./.build/agentPrompt.js");

const TYPES = ["bento", "hero_banner", "pros_cons"];
const prompt = buildAgentPrompt(TYPES);

test("the brief asks before it invents anything", () => {
  const head = prompt.slice(0, prompt.indexOf("THEN output"));
  assert.match(head, /ASK ME THIS AND WAIT/);
  assert.match(head, /real site/i);
  assert.match(head, /Write nothing else until I\nanswer/);
});

test("the brief names every field this page has", () => {
  for (const field of ["zone_id", "base_prompt", "context_prompt", "pinned_content"]) {
    assert.ok(prompt.includes(field), `the brief never mentions ${field}`);
  }
});

test("the brief carries the rules the guarantee chain enforces", () => {
  assert.match(prompt, /must already exist in what I supply/);
  assert.match(prompt, /must appear verbatim/);
  assert.match(prompt, /images\.unsplash\.com/);
});

test("the component vocabulary comes from the caller, not from a copy", () => {
  for (const type of TYPES) assert.ok(prompt.includes(type), `${type} missing`);
  assert.ok(!prompt.includes("logo_wall"), "a type nobody passed leaked in");
});

test("an agent with a known parameter opens carrying the prompt", () => {
  const chatgpt = AGENTS.find((a) => a.id === "chatgpt");
  const url = agentUrl(chatgpt, "hello there");
  assert.strictEqual(url, "https://chatgpt.com/?q=hello%20there");
  assert.strictEqual(prefills(chatgpt, "hello there"), true);
});

test("an agent without one opens on its own page", () => {
  const gemini = AGENTS.find((a) => a.id === "gemini");
  assert.strictEqual(agentUrl(gemini, "hello"), gemini.home);
  assert.strictEqual(prefills(gemini, "hello"), false);
});

test("a prompt too long for a URL degrades to the plain chat", () => {
  const chatgpt = AGENTS.find((a) => a.id === "chatgpt");
  const huge = "x".repeat(MAX_PREFILL_CHARS + 1);
  assert.strictEqual(agentUrl(chatgpt, huge), chatgpt.home);
});

test("every agent has somewhere to open", () => {
  for (const agent of AGENTS) {
    assert.match(agent.home, /^https:\/\//);
    assert.match(agent.color, /^#[0-9a-f]{6}$/i);
  }
});
