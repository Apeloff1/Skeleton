#!/usr/bin/env node
/* eslint-disable */
/**
 * patch-node-modules.js — deterministic, fail-closed compatibility/security
 * patches for third-party packages that cannot currently be fixed solely by a
 * compatible dependency bump.
 *
 * Runs automatically as a postinstall hook after every `yarn install` /
 * `yarn add` so patches survive package reinstalls. Security patches below are
 * deliberately version- and pattern-aware: if the installed package changes
 * shape, installation fails and requires explicit review instead of silently
 * leaving a known vulnerability unpatched.
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
  const src = fs.readFileSync(abs, 'utf8');
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

function patchSecurityFile(rel, vulnerablePattern, replacement, hardenedPattern) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) {
    throw new Error(`[patch-node-modules] security target missing: ${rel}`);
  }
  const src = fs.readFileSync(abs, 'utf8');
  if (hardenedPattern.test(src)) {
    skipped++;
    return;
  }
  if (!vulnerablePattern.test(src)) {
    throw new Error(`[patch-node-modules] security target changed shape; review required: ${rel}`);
  }
  const out = src.replace(vulnerablePattern, replacement);
  if (out === src || !hardenedPattern.test(out)) {
    throw new Error(`[patch-node-modules] failed to harden: ${rel}`);
  }
  fs.writeFileSync(abs, out, 'utf8');
  patched++;
  console.log(`[patch-node-modules] ✓ security ${rel}`);
}

function patchImageSizeDoS() {
  const pkgPath = path.join(ROOT, 'node_modules/image-size/package.json');
  if (!fs.existsSync(pkgPath)) {
    return;
  }
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  const version = String(pkg.version || '');
  // Current locked version. If this changes, force a review so a future package
  // layout cannot silently bypass the compensating control.
  if (version !== '1.2.1') {
    throw new Error(`[patch-node-modules] image-size ${version} requires security patch review`);
  }

  // CVE-2025-71329 / GHSA-5p2g-fcmc-qvqq: JXL/HEIF/JP2 box walks
  // must make forward progress even when a crafted box declares size zero.
  patchSecurityFile(
    'node_modules/image-size/dist/types/utils.js',
    /offset \+= box\.size;/,
    'offset += box.size > 0 ? box.size : 8;',
    /offset \+= box\.size > 0 \? box\.size : 8;/,
  );

  // CVE-2025-71330 / GHSA-w3rx-r6r6-pgpr: ICNS entries with a zero
  // declared length otherwise leave imageOffset unchanged forever.
  patchSecurityFile(
    'node_modules/image-size/dist/types/icns.js',
    /imageOffset \+= imageHeader\[1\];/g,
    'imageOffset += imageHeader[1] > 0 ? imageHeader[1] : inputLength;',
    /imageOffset \+= imageHeader\[1\] > 0 \? imageHeader\[1\] : inputLength;/,
  );
}

function patchWorkletsStaticRendering() {
  const pkgPath = path.join(ROOT, 'node_modules/react-native-worklets/package.json');
  if (!fs.existsSync(pkgPath)) {
    return;
  }
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  const version = String(pkg.version || '');

  // Expo 54 / Reanimated 4.1.x currently resolves worklets 0.5.1. The app
  // entry installs the RAF fallback before Expo Router loads, so this version
  // does not require a node_modules rewrite. Keep this exact-version and
  // entry-contract check fail-closed: any dependency drift still requires
  // explicit review.
  if (version === '0.5.1') {
    const entryPath = path.join(ROOT, 'index.js');
    if (!fs.existsSync(entryPath)) {
      throw new Error('[patch-node-modules] worklets 0.5.1 requires the static-render entry shim');
    }
    const entry = fs.readFileSync(entryPath, 'utf8');
    if (
      !entry.includes("typeof globalThis.requestAnimationFrame !== 'function'") ||
      !entry.includes("typeof globalThis.cancelAnimationFrame !== 'function'")
    ) {
      throw new Error('[patch-node-modules] worklets 0.5.1 static-render entry shim drifted');
    }
    skipped++;
    console.log('[patch-node-modules] ✓ static-render protected by frontend/index.js (worklets 0.5.1)');
    return;
  }

  if (version !== '0.13.0') {
    throw new Error(`[patch-node-modules] react-native-worklets ${version} requires static-render patch review`);
  }

  const rel = 'node_modules/react-native-worklets/lib/module/threads.js';
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) {
    throw new Error(`[patch-node-modules] worklets static-render target missing: ${rel}`);
  }

  const src = fs.readFileSync(abs, 'utf8');
  const hardenedPattern = /typeof requestAnimationFrame === ['"]function['"]/;
  if (hardenedPattern.test(src)) {
    skipped++;
    return;
  }

  const vulnerablePattern = /requestAnimationFrame\(\(\) => \{/;
  if (!vulnerablePattern.test(src)) {
    throw new Error(`[patch-node-modules] worklets static-render target changed shape; review required: ${rel}`);
  }

  const replacement =
    "(typeof requestAnimationFrame === 'function' ? requestAnimationFrame : (callback) => setTimeout(callback, 0))(() => {";
  const out = src.replace(vulnerablePattern, replacement);
  if (out === src || !hardenedPattern.test(out)) {
    throw new Error(`[patch-node-modules] failed to harden static rendering: ${rel}`);
  }

  fs.writeFileSync(abs, out, 'utf8');
  patched++;
  console.log(`[patch-node-modules] ✓ static-render ${rel}`);
}

patchImageSizeDoS();
patchWorkletsStaticRendering();

console.log(
  `[patch-node-modules] done: ${patched} patched, ${skipped} already-clean, ${missing} missing`,
);
