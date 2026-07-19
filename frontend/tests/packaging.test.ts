/**
 * Packaging boundary tests: the built package must load in a consumer we
 * don't control. require()/import run in REAL Node subprocesses (not
 * through vitest's resolver), so what passes here is what a CJS toolchain
 * (Jest, Next pages router) or an ESM one actually experiences.
 * Self-referencing `genui-framework` works because package.json has an
 * `exports` map. Requires a build first (`npm test` runs it via pretest).
 */

import { test, expect } from 'vitest';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const pkgRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const requireCjs = createRequire(import.meta.url);

const runNode = (args: string[]): string =>
  execFileSync(process.execPath, args, { cwd: pkgRoot, encoding: 'utf8' }).trim();

test('require() of the built package works for CJS consumers', () => {
  // Used to throw ERR_REQUIRE_ESM: "type": "module" made Node parse the
  // CJS dist/index.js as ESM. The exports map now routes require -> .cjs
  const out = runNode([
    '-e',
    "const m = require('genui-framework'); console.log(typeof m.GenUIZone, typeof m.useZone)",
  ]);
  expect(out).toBe('function function');
});

test('import of the built package works for ESM consumers', () => {
  const out = runNode([
    '--input-type=module',
    '-e',
    "import('genui-framework').then(m => console.log(typeof m.GenUIZone, typeof m.useZone))",
  ]);
  expect(out).toBe('function function');
});

test('the stylesheet resolves through the exports map (both documented paths)', () => {
  expect(requireCjs.resolve('genui-framework/dist/styles.css')).toMatch(/styles\.css$/);
  expect(requireCjs.resolve('genui-framework/styles.css')).toMatch(/styles\.css$/);
});

test('recharts is not in the entry bundles: it lives in a lazy chunk', () => {
  for (const entry of ['dist/index.esm.js', 'dist/index.cjs']) {
    const code = readFileSync(path.join(pkgRoot, entry), 'utf8');
    // recharts identifiers would appear verbatim (the build is unminified)
    expect(code).not.toContain('CartesianGrid');
  }
  const chunks = readdirSync(path.join(pkgRoot, 'dist/chunks'));
  expect(chunks.some((f) => f.endsWith('.esm.js'))).toBe(true);
  expect(chunks.some((f) => f.endsWith('.cjs'))).toBe(true);
});
