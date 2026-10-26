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
const crypto = require('crypto');

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
  // Metro 0.83.x depends on the synchronous 1.x API. image-size 2.x is not
  // API-compatible with that call path, so keep the exact legacy version and
  // apply the reviewed forward-progress patches below. Any version drift still
  // requires explicit review.
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

function patchBracesDepthDoS() {
  const pkgPath = path.join(ROOT, 'node_modules/braces/package.json');
  if (!fs.existsSync(pkgPath)) return;
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  const version = String(pkg.version || '');
  if (version !== '3.0.3') {
    throw new Error(`[patch-node-modules] braces ${version} requires security patch review`);
  }

  // CVE-2026-93687 / GHSA-vfj7-8cjw-p6xm: public string entry points
  // can otherwise build ASTs deep enough to exhaust recursive compile/expand
  // walkers. Preserve over-depth patterns literally instead of recursing.
  patchSecurityFile(
    'node_modules/braces/index.js',
    /braces\.parse = \(input, options = \{\}\) => parse\(input, options\);/,
    `const BRACES_SAFE_MAX_DEPTH = 256;

const exceedsSafeBraceDepth = input => {
  if (typeof input !== 'string') return false;
  let depth = 0;
  let escaped = false;
  for (const character of input) {
    if (escaped) {
      escaped = false;
      continue;
    }
    if (character === '\\\\') {
      escaped = true;
      continue;
    }
    if (character === '{') {
      depth += 1;
      if (depth > BRACES_SAFE_MAX_DEPTH) return true;
    } else if (character === '}' && depth > 0) {
      depth -= 1;
    }
  }
  return false;
};

const literalBraceAst = input => ({
  type: 'root',
  input,
  nodes: [
    { type: 'bos' },
    { type: 'text', value: input },
    { type: 'eos' }
  ]
});

braces.parse = (input, options = {}) =>
  exceedsSafeBraceDepth(input) ? literalBraceAst(input) : parse(input, options);`,
    /BRACES_SAFE_MAX_DEPTH = 256/,
  );
}

function patchHttpCacheSemanticsMaxStale() {
  const pkgPath = path.join(ROOT, 'node_modules/http-cache-semantics/package.json');
  if (!fs.existsSync(pkgPath)) return;
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  const version = String(pkg.version || '');
  if (version === '4.3.0') {
    // 4.3.0 is the reviewed patched line resolved by the frozen lockfile.
    // Do not rewrite patched upstream code; keep future version drift fail-closed.
    skipped++;
    return;
  }
  // 4.3.0 includes the upstream Vary wildcard/prototype hardening, but the
  // max-stale branch still has the same reviewed shape as 4.2.0. Keep this
  // allow-list exact so future package drift still fails closed before patching.
  if (!new Set(['4.2.0', '4.3.0']).has(version)) {
    throw new Error(`[patch-node-modules] http-cache-semantics ${version} requires security patch review`);
  }

  // CVE-2026-93748 / GHSA-ch52-4w7c-c8xp: security-zeroed shared
  // responses (for example Set-Cookie responses) must never be resurrected
  // by a client max-stale directive. Conservatively disallow max-stale when
  // maxAge() is zero.
  patchSecurityFile(
    'node_modules/http-cache-semantics/index.js',
    /if \(allowsStaleWithoutRevalidation\) \{/,
    'if (allowsStaleWithoutRevalidation && this.maxAge() > 0) {',
    /allowsStaleWithoutRevalidation && this\.maxAge\(\) > 0/,
  );
}

function patchNodeForgeNestedDigestAlgorithm() {
  const pkgPath = path.join(ROOT, 'node_modules/node-forge/package.json');
  if (!fs.existsSync(pkgPath)) return;
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  const version = String(pkg.version || '');
  if (version !== '1.4.0') {
    throw new Error(`[patch-node-modules] node-forge ${version} requires security patch review`);
  }

  // CVE-2026-85393 / GHSA-86w9-cpqp-85rv: node-forge 1.4.0 checks the
  // outer DigestInfo element count but not the nested DigestAlgorithm count.
  // This is the upstream #1152 fix shape, applied fail-closed until a patched
  // npm release exists.
  patchSecurityFile(
    'node_modules/node-forge/lib/rsa.js',
    /if\(!asn1\.validate\(obj, digestInfoValidator, capture, errors\) \|\|\s*obj\.value\.length !== 2\) \{/,
    `if(!asn1.validate(obj, digestInfoValidator, capture, errors) ||
            obj.value.length !== 2 ||
            obj.value[0].value.length !==
              (('parameters' in capture) ? 2 : 1)) {`,
    /obj\.value\[0\]\.value\.length !==/,
  );
}

function patchSprintfFormatBounds() {
  const pkgPath = path.join(ROOT, 'node_modules/sprintf-js/package.json');
  if (!fs.existsSync(pkgPath)) return;
  const version = String(JSON.parse(fs.readFileSync(pkgPath, 'utf8')).version || '');
  if (version !== '1.0.3') {
    throw new Error(`[patch-node-modules] sprintf-js ${version} requires security patch review`);
  }

  // CVE-2026-97058 / GHSA-hp3w-g68c-fv3c has no patched npm release.
  // Cap numeric precision before native Number formatting can throw for an
  // otherwise valid format string. Cap width before invoking argument functions
  // or the width-dependent Array(...).join allocation. Ordinary argparse help
  // formatting remains inside the numeric 100 / width 16 KiB limits. General
  // precision has a minimum of 1; exponential/fixed precision may be zero.
  const rel = 'node_modules/sprintf-js/src/sprintf.js';
  const target = path.join(ROOT, rel);
  const source = fs.readFileSync(target, 'utf8');
  const before = 'match = parse_tree[i] // convenience purposes only';
  const after = `${before}
                match = match.slice(0)
                if (match[6] !== undefined) {
                    if (!/^\\d+$/.test(match[6])) {
                        throw new RangeError('[sprintf] invalid format width')
                    }
                    match[6] = String(Math.min(16384, Number(match[6])))
                }
                if (/^[efg]$/.test(match[8]) && match[7] !== undefined) {
                    if (!/^\\d+$/.test(match[7])) {
                        throw new RangeError('[sprintf] invalid numeric precision')
                    }
                    match[7] = String(Math.min(100, Math.max(match[8] === 'g' ? 1 : 0, Number(match[7]))))
                }`;
  const digest = value => crypto.createHash('sha256').update(value, 'utf8').digest('hex');
  const hardenedDigest = 'b84000c68153570c8cdc4e0f62b8f96327ec34a1e7665cdf06d3cd3ca0770821';
  const sourceDigest = digest(source);
  if (sourceDigest === hardenedDigest) {
    skipped++;
    return;
  }
  const pristineDigest = '9904b0d448280bfdfcb0329bdac995883033597727404f9c058d051d9174b7c7';
  const previousDigest = '06e1ea7943ecf8d5cc342d816240156476d11effe844f6fd6504c266b2d70a1b';
  if (sourceDigest !== pristineDigest && sourceDigest !== previousDigest) {
    throw new Error('[patch-node-modules] sprintf-js security source changed; review required');
  }
  // Upgrade only the exact earlier local patch; the resulting full source must
  // still match the final digest. All other source variants fail closed.
  const hardened = sourceDigest === previousDigest
    ? source.replace(
      'match[7] = String(Math.min(100, Number(match[7])))',
      "match[7] = String(Math.min(100, Math.max(match[8] === 'g' ? 1 : 0, Number(match[7]))))",
    )
    : source.replace(before, after);
  if (hardened === source || digest(hardened) !== hardenedDigest) {
    throw new Error('[patch-node-modules] failed to harden sprintf-js formatting bounds');
  }
  fs.writeFileSync(target, hardened, 'utf8');
  patched++;
  console.log(`[patch-node-modules] ✓ security ${rel}`);
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


function patchReactNativeRnGetPolyfillsExport() {
  const pkgPath = path.join(ROOT, 'node_modules/react-native/package.json');
  if (!fs.existsSync(pkgPath)) {
    return;
  }

  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  const version = String(pkg.version || '');
  // Both supported package layouts must satisfy the same exact export-shape
  // checks below; unknown versions remain fail-closed pending review.
  if (version !== '0.81.5' && version !== '0.88.0') {
    throw new Error(
      `[patch-node-modules] react-native ${version} requires rn-get-polyfills export review`,
    );
  }

  const rel = 'node_modules/react-native/rn-get-polyfills.js';
  const targetPath = path.join(ROOT, rel);
  if (!fs.existsSync(targetPath)) {
    throw new Error(`[patch-node-modules] React Native polyfills target missing: ${rel}`);
  }

  if (!pkg.exports || typeof pkg.exports !== 'object' || Array.isArray(pkg.exports)) {
    throw new Error('[patch-node-modules] React Native exports map changed shape');
  }

  const exportKey = './rn-get-polyfills';
  const expectedTarget = './rn-get-polyfills.js';
  if (Object.prototype.hasOwnProperty.call(pkg.exports, exportKey)) {
    if (pkg.exports[exportKey] !== expectedTarget) {
      throw new Error('[patch-node-modules] React Native rn-get-polyfills export changed shape');
    }
    skipped++;
    return;
  }

  pkg.exports[exportKey] = expectedTarget;
  fs.writeFileSync(pkgPath, `${JSON.stringify(pkg, null, 2)}\n`, 'utf8');
  patched++;
  console.log('[patch-node-modules] ✓ react-native rn-get-polyfills export');
}

function patchExpoStaticIndexPath() {
  const pkgPath = path.join(ROOT, 'node_modules/@expo/cli/package.json');
  if (!fs.existsSync(pkgPath)) return;
  const version = JSON.parse(fs.readFileSync(pkgPath, 'utf8')).version;
  // SDK 54 shipped both CLI versions with the same guarded static-index path.
  // Future releases still require an explicit exact-version and source review.
  if (!new Set(['54.0.27', '54.0.28']).has(version)) {
    throw new Error(`[patch-node-modules] Expo CLI ${version} requires static path review`);
  }
  const target = path.join(ROOT, 'node_modules/@expo/cli/build/src/export/exportStaticAsync.js');
  const source = fs.readFileSync(target, 'utf8');
  // The upstream optional-slash regex strips "index" from "story-index",
  // rendering /story- into story-index.html and breaking root hydration.
  const before = "pathname: filePathLocation.replace(/(\\/?index)?$/, '')";
  const after = "pathname: filePathLocation === 'index' ? '' : filePathLocation.replace(/\\/index$/, '')";
  if (source.includes(after)) {
    // A mixed or duplicated result is not an idempotent hardened source.
    // Refuse partial rewrites rather than leaving an unsafe route behind.
    if (source.includes(before) || source.split(after).length !== 2) {
      throw new Error('[patch-node-modules] Expo static path contains ambiguous mixed patch states');
    }
    skipped++;
    return;
  }
  if (source.split(before).length !== 2) {
    throw new Error('[patch-node-modules] Expo static path target changed shape; review required');
  }
  const hardened = source.replace(before, after);
  if (!hardened.includes(after) || hardened.includes(before)) {
    throw new Error('[patch-node-modules] Expo static path patch postcondition failed');
  }
  fs.writeFileSync(target, hardened, 'utf8');
  patched++;
  console.log('[patch-node-modules] ✓ Expo static index path segment');
}

patchImageSizeDoS();
patchBracesDepthDoS();
patchHttpCacheSemanticsMaxStale();
patchNodeForgeNestedDigestAlgorithm();
patchSprintfFormatBounds();
patchWorkletsStaticRendering();
patchReactNativeRnGetPolyfillsExport();
patchExpoStaticIndexPath();

console.log(
  `[patch-node-modules] done: ${patched} patched, ${skipped} already-clean, ${missing} missing`,
);
