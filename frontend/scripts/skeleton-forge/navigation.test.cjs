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
  const reg = read('src/utils/routeRegistry.ts');
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

test('studio route, registry and menu agree', () => {
  const route = read('app/skeleton-studio.tsx');
  assert.match(route, /FoundationScreen/);
  assert.match(route, /\/skeleton-forge/);
  assert.match(route, /\/setup/);
  const reg = read('src/utils/routeRegistry.ts');
  const hits = reg.match(/path: '\/skeleton-studio'/g) || [];
  assert.equal(hits.length, 1);
  const menu = read('app/menu.tsx');
  const card = menu.split('\n').find((l) => l.includes("id: 'skeletonStudio'"));
  assert.ok(card, 'studio menu card missing');
  assert.match(card, /route: '\/skeleton-studio'/);
});

test('Studio ↔ Forge route uses an explicit source-bound return, not a blind global draft', () => {
  const route = read('app/skeleton-forge.tsx');
  const studio = read('src/skeletonForge/components/foundation/FoundationScreen.tsx');
  const cockpit = read('src/skeletonForge/components/ForgeCockpitView.tsx');
  assert.match(studio, /handoffFromStudio\(project\.questionnaire, project\.id, project\.updatedAt\)/);
  assert.match(studio, /storeCreatorBridge\(envelope\)/);
  assert.match(studio, /reconcileStudioReturn\(/);
  assert.match(studio, /recoverStudioReturnAsCopy\(/);
  assert.match(route, /handoffToStudio\(draft, incoming\)/);
  assert.match(route, /router\.replace\('\/skeleton-studio'/);
  assert.match(cockpit, /testID="cockpit-save-to-studio"/);
  assert.match(route, /handoffFromForge\(draft, Date\.now\(\), incoming\)/);
});
