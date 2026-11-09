'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const compose = require('./fixtures/compose.json');

const G = load('src/skeletonForge/graph.ts');

test('highlightVision marks exactly the server-matched words and preserves text', () => {
  const segs = G.highlightVision(compose.vision, compose.matches);
  assert.equal(segs.map((s) => s.text).join(''), compose.vision);
  const hits = segs.filter((s) => s.features.length).map((s) => `${s.text}:${s.features.join('+')}`);
  assert.deepEqual(hits, [
    'craft:crafting', 'gear:crafting', 'save:persistence', 'stash:persistence', 'survive:extraction', 'storm:collapse',
  ]);
  // "combat" is negated server-side ("no combat") and must not light up.
  assert.ok(!hits.some((h) => h.startsWith('combat')));
});

test('highlightVision is case-insensitive and merges plain runs', () => {
  const segs = G.highlightVision('SHOOT the Boss!', { combat: ['shoot', 'boss'] });
  assert.deepEqual(segs, [
    { text: 'SHOOT', features: ['combat'] },
    { text: ' the ', features: [] },
    { text: 'Boss', features: ['combat'] },
    { text: '!', features: [] },
  ]);
  assert.deepEqual(G.highlightVision('', {}), []);
  assert.deepEqual(G.highlightVision('plain words', null), [{ text: 'plain words', features: [] }]);
});

test('triggerIndex keeps unknown server features instead of dropping them', () => {
  const idx = G.triggerIndex({ weather: ['rain'], combat: ['rain'] });
  assert.deepEqual(idx.get('rain'), ['combat', 'weather']);
});

test('explainComposition links triggers and wiring per component', () => {
  const rows = G.explainComposition(compose);
  assert.deepEqual(rows.map((r) => r.feature), ['player', 'crafting', 'collapse', 'extraction', 'persistence']);
  const op = rows[0];
  assert.deepEqual(op.feeds.sort(), ['collapse', 'vault']);
  const vault = rows.find((r) => r.instanceId === 'vault');
  assert.deepEqual(vault.triggers, ['save', 'stash']);
  assert.deepEqual(vault.fedBy, ['operator']);
  assert.equal(vault.meta.label, 'Persistence');
});

test('describeComposition gives a screen-reader sentence incl. fallback', () => {
  const s = G.describeComposition(compose);
  assert.match(s, /^4 systems composed: Crafting \(from “craft”, “gear”\)/);
  assert.match(s, /2 wires\.$/);
  const fb = G.describeComposition({ ...compose, fallback: true, matches: {} });
  assert.match(fb, /fallback loop/);
  assert.equal(G.describeComposition(null), 'No composition yet.');
});

test('computeDepths: operator at 0, wired sinks deeper, cycles bounded', () => {
  const comps = [
    { instance_id: 'operator', kind: 'player', feature: 'player' },
    { instance_id: 'spawner', kind: 'enemy_spawner', feature: 'combat' },
    { instance_id: 'collapse', kind: 'collapse', feature: 'collapse' },
    { instance_id: 'extract', kind: 'extract', feature: 'extraction' },
  ];
  const wires = [
    { from: ['operator', 'intent'], to: ['spawner', 'tick'] },
    { from: ['spawner', 'spawn'], to: ['collapse', 'tick'] },
  ];
  const d = G.computeDepths(comps, wires);
  assert.deepEqual(Object.fromEntries(d), { operator: 0, spawner: 1, collapse: 2, extract: 1 });
  const cyc = G.computeDepths(comps.slice(0, 2), [...wires.slice(0, 1), { from: ['spawner', 'x'], to: ['operator', 'y'] }]);
  assert.ok([...cyc.values()].every((v) => v <= 2));
});

test('layoutGraph is horizontal on wide screens and vertical on phones', () => {
  const wide = G.layoutGraph(compose.components, compose.wires, { width: 900 });
  assert.equal(wide.orientation, 'horizontal');
  assert.equal(wide.nodes.length, 5);
  assert.equal(wide.edges.length, 2);
  const op = wide.nodes.find((n) => n.id === 'operator');
  const vault = wide.nodes.find((n) => n.id === 'vault');
  assert.ok(vault.x > op.x, 'wired target sits right of its source');
  assert.equal(wide.nodes.find((n) => n.id === 'forge').wired, false);
  assert.match(wide.edges[0].d, /^M[\d.]+,[\d.]+ C/);

  const narrow = G.layoutGraph(compose.components, compose.wires, { width: 360 });
  assert.equal(narrow.orientation, 'vertical');
  for (const n of narrow.nodes) assert.ok(n.x >= 0 && n.x + n.w <= 360, `node ${n.id} fits the phone width`);
  const opN = narrow.nodes.find((n) => n.id === 'operator');
  assert.ok(narrow.nodes.filter((n) => n.id !== 'operator').every((n) => n.y > opN.y));
});

test('layoutGraph tolerates empty and malformed payloads', () => {
  assert.deepEqual(G.layoutGraph([], [], { width: 400 }).nodes, []);
  const l = G.layoutGraph(compose.components, [{ from: null, to: ['x'] }, { from: ['ghost', 'p'], to: ['vault', 'write'] }], { width: 800 });
  assert.equal(l.edges.length, 0);
});

test('layout is deterministic', () => {
  const a = G.layoutGraph(compose.components, compose.wires, { width: 720 });
  const b = G.layoutGraph(compose.components, compose.wires, { width: 720 });
  assert.deepEqual(a, b);
});

test('featureMeta/humanize fall back gracefully', () => {
  assert.equal(G.featureMeta('combat').label, 'Combat');
  assert.equal(G.featureMeta('weather_front').label, 'Weather Front');
  assert.equal(G.humanize('extraction_now'), 'Extraction Now');
  assert.equal(G.humanize('a~b@0.50'), 'A B@0.50');
});
