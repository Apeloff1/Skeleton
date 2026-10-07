/**
 * Zero-dependency component test harness for src/skeletonForge.
 *
 * - Transpiles .ts/.tsx on the fly with the Babel toolchain Expo already
 *   ships (preset-typescript + preset-react + modules-commonjs).
 * - Aliases `react-native` → `react-native-web` so components render to
 *   real DOM markup through react-dom/server (roles, aria-labels, text).
 * - Stubs deep `react-native/Libraries/*` imports used by native-only libs.
 *
 * Tests import this first, then `load('src/…')` and `render(<El/>)`.
 */
'use strict';
const path = require('node:path');
const fs = require('node:fs');
const Module = require('node:module');

const ROOT = path.resolve(__dirname, '..', '..');
const requireFromRoot = Module.createRequire(path.join(ROOT, 'package.json'));
const babel = requireFromRoot('@babel/core');
const PRESETS = [
  [requireFromRoot.resolve('@babel/preset-typescript'), { isTSX: true, allExtensions: true }],
  [requireFromRoot.resolve('@babel/preset-react'), { runtime: 'automatic' }],
];
const PLUGINS = [requireFromRoot.resolve('@babel/plugin-transform-modules-commonjs')];
const STUB = path.join(__dirname, 'rn-deep-stub.cjs');
const SRC_EXT = ['.tsx', '.ts'];

const origResolve = Module._resolveFilename;
Module._resolveFilename = function resolve(request, parent, ...rest) {
  if (request === 'react-native') request = 'react-native-web';
  else if (request.startsWith('react-native/')) return STUB;
  if ((request.startsWith('.') || request.startsWith('/')) && parent && parent.filename) {
    const base = path.resolve(path.dirname(parent.filename), request);
    if (!path.extname(base) || !fs.existsSync(base)) {
      for (const ext of SRC_EXT) {
        if (fs.existsSync(base + ext)) return base + ext;
        const idx = path.join(base, 'index' + ext);
        if (fs.existsSync(idx)) return idx;
      }
    }
  }
  return origResolve.call(this, request, parent, ...rest);
};

for (const ext of SRC_EXT) {
  Module._extensions[ext] = function compile(module, filename) {
    const src = fs.readFileSync(filename, 'utf8');
    const out = babel.transformSync(src, {
      filename, babelrc: false, configFile: false, presets: PRESETS, plugins: PLUGINS, sourceMaps: 'inline',
    });
    module._compile(out.code, filename);
  };
}

// react-native-web / react-native-svg emit dev-only prop warnings when
// rendered on the server; keep test output readable, surface real errors.
const NOISE = [/does not recognize the `/, /is using incorrect casing/, /Invalid DOM property/, /Received `(true|false)` for a non-boolean/, /useLayoutEffect does nothing on the server/, /unknown event handler property/i, /React does not recognize/];
const origError = console.error;
console.error = (...args) => {
  const msg = String(args[0] ?? '');
  if (NOISE.some((re) => re.test(msg))) return;
  origError(...args);
};

const React = requireFromRoot('react');
const { renderToStaticMarkup } = requireFromRoot('react-dom/server');

function load(rel) {
  return require(path.join(ROOT, rel));
}

function render(element) {
  return renderToStaticMarkup(element);
}

/** Extract visible text (tags stripped, entities decoded, whitespace folded). */
function text(html) {
  return html
    .replace(/<[^>]+>/g, ' ')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#x27;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

/** All values of an attribute (e.g. aria-label) in document order. */
function attrs(html, name) {
  const re = new RegExp(`${name}="([^"]*)"`, 'g');
  const out = [];
  let m;
  while ((m = re.exec(html))) out.push(m[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#x27;/g, "'"));
  return out;
}

module.exports = { React, load, render, text, attrs, h: React.createElement, ROOT };
