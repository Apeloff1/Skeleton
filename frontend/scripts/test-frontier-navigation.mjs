import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  buildLevelStack, classifyLevel, clampZoom, stepZoom, canZoom, viewportFor, initialView,
  switchLevel, jumpToLevel, panView, portalsFrom, travelThroughPortal, MAX_ZOOM,
} from '../src/product/frontierMinimap.ts';

const layers = [
  { id: 'sky', size: [32, 32], elevation_m: 400 },
  { id: 'surface', size: [64, 64], elevation_m: 10 },
  { id: 'caves', size: [16, 16], elevation_m: -40 },
  { id: 'bad', size: [0, 5], elevation_m: 0 },
  { id: 'surface', size: [8, 8], elevation_m: 0 },
];
const portals = [
  { portal_id: 'p-lift', from: { layer: 'surface', x: 10, y: 10 }, to: { layer: 'sky', x: 1, y: 2 }, mode: 'elevator', bidirectional: true },
  { portal_id: 'p-hole', from: { layer: 'surface', x: 5, y: 5 }, to: { layer: 'caves', x: 3, y: 3 }, mode: 'drop', bidirectional: false },
  { portal_id: 'p-oob', from: { layer: 'surface', x: 1, y: 1 }, to: { layer: 'caves', x: 99, y: 3 }, mode: 'drop', bidirectional: true },
];

test('classifies and orders levels bottom to top, dropping invalid/duplicate layers', () => {
  assert.equal(classifyLevel(-1), 'underground');
  assert.equal(classifyLevel(0), 'surface');
  assert.equal(classifyLevel(120), 'sky');
  assert.equal(classifyLevel(NaN), 'surface');
  const stack = buildLevelStack(layers);
  assert.deepEqual(stack.map(l => [l.id, l.kind, l.index]), [['caves', 'underground', 0], ['surface', 'surface', 1], ['sky', 'sky', 2]]);
});

test('zoom is clamped and stepped in powers of two', () => {
  assert.equal(clampZoom(0), 1);
  assert.equal(clampZoom(1e9), MAX_ZOOM);
  assert.equal(stepZoom(1, 1), 2);
  assert.equal(stepZoom(MAX_ZOOM, 1), MAX_ZOOM);
  assert.equal(canZoom(1, -1), false);
  assert.equal(canZoom(1, 1), true);
});

test('viewport always stays inside the layer', () => {
  const layer = { id: 's', size: [64, 64], elevation_m: 0 };
  assert.deepEqual(viewportFor({ layer: 's', zoom: 1, center: [0, 0] }, layer), { x0: 0, y0: 0, x1: 63, y1: 63, widthTiles: 64, heightTiles: 64 });
  const vp = viewportFor({ layer: 's', zoom: 4, center: [63, 63] }, layer);
  assert.equal(vp.x1, 63); assert.equal(vp.widthTiles, 16);
  const panned = panView({ layer: 's', zoom: 4, center: [60, 60] }, layer, 5, 5);
  assert.deepEqual(panned.center, [63, 63]);
});

test('level switching starts on surface, keeps relative position, stops at ends', () => {
  const stack = buildLevelStack(layers);
  const v = initialView(stack);
  assert.equal(v.layer, 'surface');
  const down = switchLevel(stack, { ...v, center: [63, 0] }, -1);
  assert.equal(down.layer, 'caves'); assert.deepEqual(down.center, [15, 0]);
  assert.equal(switchLevel(stack, down, -1), down);
  assert.equal(jumpToLevel(stack, v, 'sky').layer, 'sky');
  assert.equal(jumpToLevel(stack, v, 'nope'), v);
  assert.equal(initialView([]), null);
});

test('portals only list declared, in-bounds endpoints and respect direction', () => {
  const stack = buildLevelStack(layers);
  assert.deepEqual(portalsFrom(portals, stack, 'surface').map(p => p.portal.portal_id), ['p-hole', 'p-lift']);
  assert.deepEqual(portalsFrom(portals, stack, 'sky').map(p => p.portal.portal_id), ['p-lift']);
  assert.deepEqual(portalsFrom(portals, stack, 'caves'), []);
  const v = initialView(stack);
  const up = travelThroughPortal(portals, stack, v, 'p-lift');
  assert.deepEqual([up.layer, up.center], ['sky', [1, 2]]);
  const back = travelThroughPortal(portals, stack, up, 'p-lift');
  assert.deepEqual([back.layer, back.center], ['surface', [10, 10]]);
  assert.equal(travelThroughPortal(portals, stack, v, 'p-oob'), v);
});
