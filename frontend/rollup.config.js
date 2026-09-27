import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import typescript from '@rollup/plugin-typescript';
import dts from 'rollup-plugin-dts';
import peerDepsExternal from 'rollup-plugin-peer-deps-external';
import postcss from 'rollup-plugin-postcss';
import { copyFileSync, renameSync, rmSync } from 'node:fs';

const watch = process.env.ROLLUP_WATCH === 'true';
// A build writes into a staging directory and swaps it in as dist only after
// every output is written: a failed build leaves the previous dist in place.
const out = watch ? 'dist' : 'build';
if (!watch) rmSync(out, { recursive: true, force: true });

const finish = {
  name: 'finish',
  writeBundle() {
    copyFileSync(`${out}/index.d.ts`, `${out}/index.d.cts`);
    if (watch) return;
    rmSync('dist', { recursive: true, force: true });
    renameSync(out, 'dist');
  },
};

const onwarn = (warning, warn) => {
  const id = warning.id || (warning.ids && warning.ids[0]) || '';
  if (
    (warning.code === 'MODULE_LEVEL_DIRECTIVE' || warning.code === 'CIRCULAR_DEPENDENCY') &&
    /node_modules/.test(id + (warning.message || ''))
  ) {
    return;
  }
  warn(warning);
};

export default [
  {
    input: 'src/index.ts',
    onwarn,
    output: [
      {
        dir: out,
        format: 'cjs',
        entryFileNames: 'index.cjs',
        chunkFileNames: 'chunks/[name]-[hash].cjs',
        sourcemap: watch,
        exports: 'named',
      },
      {
        dir: out,
        format: 'esm',
        entryFileNames: 'index.esm.js',
        chunkFileNames: 'chunks/[name]-[hash].esm.js',
        sourcemap: watch,
        exports: 'named',
      },
    ],
    plugins: [
      peerDepsExternal(),
      resolve(),
      commonjs(),
      typescript({ tsconfig: './tsconfig.json', outDir: out, declarationDir: out }),
      postcss({
        extract: 'styles.css',
        minimize: true,
      }),
    ],
    external: [/^react($|\/)/, /^react-dom($|\/)/],
  },
  {
    input: `${out}/index.d.ts`,
    output: [{ file: `${out}/index.d.ts`, format: 'esm' }],
    plugins: [dts(), finish],
    external: [/\.css$/],
  },
];
