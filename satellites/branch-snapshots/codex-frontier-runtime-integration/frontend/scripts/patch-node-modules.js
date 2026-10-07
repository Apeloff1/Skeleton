#!/usr/bin/env node
/* eslint-disable */
/**
 * patch-node-modules.js — strip `import.meta.env` from third-party packages
 * that ship ESM bundles with ESM-only syntax. Metro's web bundler treats these
 * as scripts and throws `Cannot use 'import.meta' outside a module`, which
 * crashes the whole React tree before render (black screen / blank UI).
 *
 * Runs automatically as a postinstall hook after every `yarn install` /
 * `yarn add` so patches survive package reinstalls.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

const TARGETS = [
  // Zustand 4.x and 5.x ship ESM bundles with import.meta.env guards that
  // metro web can't handle. Safe to replace — they're only used for DEV
  // mode detection, which metro evaluates elsewhere.
  'node_modules/zustand/esm/middleware.mjs',
  'node_modules/zustand/esm/vanilla.mjs',
  'node_modules/zustand/esm/index.mjs',
  'node_modules/zustand/esm/context.mjs',
  'node_modules/zustand/esm/shallow.mjs',
  'node_modules/zustand/esm/traditional.mjs',
  // Zustand middleware subdirectory (v5)
  'node_modules/zustand/esm/middleware/devtools.mjs',
  'node_modules/zustand/esm/middleware/persist.mjs',
  'node_modules/zustand/esm/middleware/combine.mjs',
  'node_modules/zustand/esm/middleware/immer.mjs',
  'node_modules/zustand/esm/middleware/redux.mjs',
  'node_modules/zustand/esm/middleware/subscribeWithSelector.mjs',
];

const PATTERNS = [
  // Most common zustand pattern
  { find: 'import.meta.env ? import.meta.env.MODE : void 0', replace: '"production"' },
  // Fallback: any bare `import.meta.env` reference
  { find: /import\.meta\.env/g, replace: '({})' },
  // Any `import.meta.url` references
  { find: /import\.meta\.url/g, replace: '""' },
  // Standalone `import.meta` (rare, last-resort)
  { find: /import\.meta\b/g, replace: '({})' },
];

let patched = 0;
let skipped = 0;
let missing = 0;

for (const rel of TARGETS) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) {
    missing++;
    continue;
  }
  let src = fs.readFileSync(abs, 'utf8');
  if (!/import\.meta/.test(src)) {
    skipped++;
    continue;
  }
  let out = src;
  for (const p of PATTERNS) {
    if (typeof p.find === 'string') {
      out = out.split(p.find).join(p.replace);
    } else {
      out = out.replace(p.find, p.replace);
    }
  }
  if (out !== src) {
    fs.writeFileSync(abs, out, 'utf8');
    patched++;
    console.log(`[patch-node-modules] ✓ ${rel}`);
  } else {
    skipped++;
  }
}

console.log(
  `[patch-node-modules] done: ${patched} patched, ${skipped} already-clean, ${missing} missing`
);
