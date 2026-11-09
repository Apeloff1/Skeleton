'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');
const compose = require('./fixtures/compose.json');

const ComponentGraph = load('src/skeletonForge/components/ComponentGraph.tsx').default;
const VisionHighlight = load('src/skeletonForge/components/VisionHighlight.tsx').default;
const ComposePanel = load('src/skeletonForge/components/ComposePanel.tsx').default;

test('ComponentGraph renders one accessible node per component with its triggers', () => {
  const html = render(h(ComponentGraph, { result: compose, initialWidth: 900 }));
  const labels = attrs(html, 'aria-label');
  const nodeLabels = labels.filter((l) => / system, component /.test(l));
  assert.equal(nodeLabels.length, 5);
  assert.ok(nodeLabels.some((l) => l.startsWith('Persistence system, component vault') && l.includes('Triggered by save, stash')));
  assert.ok(nodeLabels.some((l) => l.startsWith('Crafting system') && l.includes('Not wired to other systems')));
  assert.ok(nodeLabels.some((l) => l.startsWith('Player system') && l.includes('Always present')));
  // Graph container summarises the composition for screen readers.
  assert.ok(labels.some((l) => l.startsWith('Component graph. 4 systems composed')));
  // Edges carry port labels.
  assert.match(html, /intent → tick/);
  assert.match(html, /state → write/);
});

test('ComponentGraph provenance list names the words behind each system', () => {
  const html = render(h(ComponentGraph, { result: compose, initialWidth: 900 }));
  assert.ok(attrs(html, 'aria-label').includes('Why each system is here'));
  const t = text(html);
  assert.match(t, /Collapse collapse run-ending fail clock storm/);
  assert.match(t, /Extraction extract win condition: get out with the haul survive/);
  assert.doesNotMatch(t, /fallback — not from your words/);
});

test('ComponentGraph marks the selected node and dims unrelated ones', () => {
  const html = render(h(ComponentGraph, { result: compose, initialWidth: 900, selected: 'vault', onSelect: () => {} }));
  const labels = attrs(html, 'aria-label');
  assert.ok(labels.some((l) => l.startsWith('Persistence system, component vault') && l.endsWith('Selected.')));
  assert.ok(!labels.some((l) => l.startsWith('Crafting system') && l.endsWith('Selected.')));
  // Unrelated nodes (not the selection or its neighbours) are dimmed.
  const forge = html.match(/<button[^>]*data-testid="graph-node-forge"[^>]*>/)[0];
  const op = html.match(/<button[^>]*data-testid="graph-node-operator"[^>]*>/)[0];
  const dimClass = (tag) => /r-opacity-/.test(tag);
  assert.ok(dimClass(forge), 'unrelated node dimmed');
  assert.ok(!dimClass(op), 'neighbour (operator feeds vault) stays lit');
});

test('ComponentGraph shows the fallback warning and empty state', () => {
  const fb = render(h(ComponentGraph, { result: { ...compose, fallback: true, matches: {} }, initialWidth: 600 }));
  assert.match(text(fb), /No recognised systems in the vision/);
  assert.match(fb, /role="alert"/);
  assert.match(text(fb), /fallback — not from your words/);
  const empty = render(h(ComponentGraph, { result: null }));
  assert.match(text(empty), /Type a vision to see which systems it composes/);
  assert.ok(attrs(empty, 'aria-label').includes('No composition yet.'));
});

test('ComponentGraph phone layout keeps every node inside the viewport', () => {
  const html = render(h(ComponentGraph, { result: compose, initialWidth: 340 }));
  const lefts = [...html.matchAll(/left:\s*(\d+)px/g)].map((m) => Number(m[1]));
  assert.ok(lefts.length >= 5);
  assert.ok(lefts.every((x) => x >= 0 && x < 340));
});

test('VisionHighlight labels each trigger word with the system it spawns', () => {
  const html = render(h(VisionHighlight, { vision: compose.vision, matches: compose.matches }));
  assert.equal(text(html).replace(/[⚒▣⇪⏳\s]/g, ''), compose.vision.replace(/\s/g, ''));
  const labels = attrs(html, 'aria-label');
  assert.deepEqual(labels, [
    'craft, triggers Crafting', 'gear, triggers Crafting', 'save, triggers Persistence',
    'stash, triggers Persistence', 'survive, triggers Extraction', 'storm, triggers Collapse',
  ]);
  assert.match(text(render(h(VisionHighlight, { vision: '', matches: null }))), /will appear here/);
});

test('ComposePanel wires input, summary, highlight and graph', () => {
  const html = render(h(ComposePanel, {
    vision: compose.vision, onChangeVision: () => {},
    compose: { result: compose, vision: compose.vision, loading: false, error: null }, initialWidth: 800,
  }));
  assert.match(html, /aria-label="Game vision"/);
  assert.match(text(html), /4 systems: crafting, collapse, extraction, persistence/);
  assert.match(text(html), /Preview blueprint bp-12a59071861a · 2 wires/);
  const err = render(h(ComposePanel, { vision: 'x', compose: { result: null, vision: '', loading: false, error: 'HTTP 422' }, editable: false }));
  assert.match(text(err), /Compose failed: HTTP 422/);
  assert.doesNotMatch(err, /aria-label="Game vision"/);
  assert.match(text(err), /Composing…/);
});
