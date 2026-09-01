// Correctness only. Prettier is deliberately absent — see docs/open.md.
//
// The hazard that keeps a formatter out of `cli/canvas/static/`: `htm` has no
// notion of a comment, and whitespace in tag position silently mangles an
// element's children. One comment inside a `<div>` opening tag once removed an
// `<input>` from the DOM entirely, and only rendering the page found it. A tool
// that reflows `html`…`` templates is that same bug with authority behind it.
// ESLint reads; Prettier rewrites. They were never one decision.

import js from '@eslint/js';
import globals from 'globals';

const correctness = {
  // Formatting rules are omitted on purpose rather than forgotten: with no
  // formatter in the repo, a style rule here is a fight nothing can settle.
  'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
  'no-console': 'off', // the shell logs to the terminal it was started from
  eqeqeq: ['error', 'always'],
  'no-var': 'error',
  'prefer-const': 'error',
};

export default [
  js.configs.recommended,
  {
    // Vendored code is exempt, the same rule tests/test_theme.py's hex scan
    // uses: it is not ours to keep a house style out of.
    ignores: ['cli/canvas/static/vendor/**', '**/node_modules/**', '.venv/**'],
  },
  {
    // The canvas: ES modules the browser loads directly. No build step, no
    // bundler, no Node — a `require` here would be a real error.
    files: ['cli/canvas/static/**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: globals.browser,
    },
    rules: correctness,
  },
  {
    // The Electron shell. Not split further by process: `preload.js` bridges
    // both worlds by design, and `main.js` holds renderer-shaped callbacks, so
    // a strict main/renderer split here would flag correct code. Revisit if the
    // shell grows files that are unambiguously one or the other.
    files: ['shell/**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'commonjs',
      globals: { ...globals.node, ...globals.browser },
    },
    rules: correctness,
  },
  {
    // The render scripts under `docs/design/`. Plain Node ES modules — they
    // spawn `sb ui` and drive Chromium over the DevTools Protocol to
    // photograph the surface, so they are Node and never the browser, even
    // though what they operate is a page.
    //
    // Without this block they fall through to `js.configs.recommended` with no
    // globals declared at all, and every `console`, `fetch`, `process` and
    // `setTimeout` is a `no-undef` error. The lint stayed green while the
    // directory was pictures only.
    files: ['docs/design/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: globals.node,
    },
    rules: correctness,
  },
  {
    // The design-sync scripts. They build the upload bundle for
    // claude.ai/design and verify it by rendering: Node drives Playwright, but
    // the callbacks handed to `page.evaluate` are serialised and run *in the
    // page*, so `document` and `getComputedStyle` are as real here as
    // `process` is. That is why this block declares both worlds where
    // `docs/design/**` next door declares only Node — those scripts speak CDP
    // and never close over a browser global.
    files: ['.design-sync/scripts/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.node, ...globals.browser },
    },
    rules: correctness,
  },
];
