/**
 * Tests for the bridge between the Playground theme and the per-tenant
 * theme store (lib/theme.ts): tokens out, a stored theme back in.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DEFAULT_STUDIO_THEME,
  genUIThemeFromTokens,
  themeFromTokens,
  themeTokens,
} = require("./.build/theme.js");

test("a full theme survives the round trip through the store shape", () => {
  const edited = {
    ...DEFAULT_STUDIO_THEME,
    mode: "light",
    accentColor: "#ff0055",
    borderRadius: "0px",
    spacingScale: "lg",
    surface1: "#0a0a0c",
    textOnAccent: "#ffffff",
  };
  assert.deepEqual(themeFromTokens(themeTokens(edited)), edited);
});

test("unset brand colors stay unset, not empty overrides", () => {
  const tokens = themeTokens(DEFAULT_STUDIO_THEME);
  assert.equal("surface1" in tokens, false);
  assert.equal(themeFromTokens(tokens).surface1, "");
  assert.deepEqual(themeFromTokens(tokens), DEFAULT_STUDIO_THEME);
});

test("a stored value that could inject CSS is dropped", () => {
  const loaded = themeFromTokens({
    accentColor: "red; background: url(//evil.test/x)",
    borderRadius: "24px; position: fixed",
    fontFamily: "Inter; } body { display: none",
  });
  assert.equal(loaded.accentColor, DEFAULT_STUDIO_THEME.accentColor);
  assert.equal(loaded.borderRadius, DEFAULT_STUDIO_THEME.borderRadius);
  assert.equal(loaded.fontFamily, DEFAULT_STUDIO_THEME.fontFamily);
});

test("the theme prop carries only what the tenant saved", () => {
  assert.deepEqual(genUIThemeFromTokens({ accentColor: "#ff0055", mode: "light" }), {
    accentColor: "#ff0055",
    mode: "light",
  });
});

test("an invalid stored token never reaches the theme prop", () => {
  assert.deepEqual(
    genUIThemeFromTokens({
      accentColor: "red; background: url(//evil.test/x)",
      mode: "light",
    }),
    { mode: "light" },
  );
});

test("a token outside the contract is ignored", () => {
  const loaded = themeFromTokens({
    accentColor: "#123456",
    backgroundImage: "url(//evil.test/x)",
  });
  assert.equal(loaded.accentColor, "#123456");
  assert.equal("backgroundImage" in loaded, false);
});
