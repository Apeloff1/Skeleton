'use strict';
// /skeleton-forge is reachable: route file, route registry and menu card agree.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', '..');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

test('route file exists and deep-links tabs', () => {
  const src = read('app/skeleton-forge.tsx');
  assert.match(src, /ForgeCockpitScreen/);
  assert.match(src, /parseTabParam\(params\.tab\)/);
});

test('route registry declares /skeleton-forge exactly once under build', () => {
  const reg = read('utils/routeRegistry.ts');
  const hits = reg.match(/path: '\/skeleton-forge'[^}]*/g) || [];
  assert.equal(hits.length, 1);
  assert.match(hits[0], /category: 'build'/);
});

test('menu exposes a Skeleton Forge card pointing at the route', () => {
  const menu = read('app/menu.tsx');
  const card = menu.split('\n').find((l) => l.includes("id: 'skeletonForge'"));
  assert.ok(card, 'menu card missing');
  assert.match(card, /route: '\/skeleton-forge'/);
});
