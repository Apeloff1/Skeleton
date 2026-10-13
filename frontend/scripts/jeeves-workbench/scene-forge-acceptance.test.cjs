const { test } = require('node:test');
const { assert } = require('./helpers.cjs');
const { acceptSceneForgeResponse } = require('../../src/product/sceneForgeAcceptance.ts');

const request = [
  { category: 'house', count: 8 },
  { category: 'npc', count: 6 },
];
const receipt = (change = {}) => ({
  build_id: 'game-A',
  era: 'modern',
  era_label: 'Modern',
  composed: [{ category: 'house', count: 8 }, { category: 'npc', count: 6 }],
  total: 14,
  primary: 14,
  variants: 0,
  mounted: true,
  clamped: false,
  ...change,
});
const evaluate = (raw, items = request, ok = true) =>
  acceptSceneForgeResponse(ok, raw, 'game-A', items);

test('genuine universal forge mounted receipt is accepted', () => {
  assert.deepEqual(evaluate(receipt()), {
    accepted: true, reason: null, count: 14, clamped: false,
  });
});

test('an HTTP failure or arbitrary JSON is never scene success', () => {
  assert.equal(evaluate(receipt(), request, false).accepted, false);
  for (const raw of [null, {}, [], { error: 'unavailable' }, 'ok', 14]) {
    assert.equal(evaluate(raw).accepted, false);
  }
});

test('receipt identity and actual mounted state are mandatory', () => {
  assert.equal(evaluate(receipt({ build_id: 'foreign-game' })).accepted, false);
  assert.equal(evaluate(receipt({ mounted: false })).accepted, false);
  assert.equal(evaluate(receipt({ mounted: undefined })).accepted, false);
  assert.equal(evaluate(receipt({ clamped: undefined })).accepted, false);
});

test('counts, variants and primary accounting must be internally consistent', () => {
  for (const change of [
    { total: 0 }, { total: 2 },
    { total: 15 }, { total: NaN },
    { total: '14' }, { variants: -1 },
    { primary: 0 }, { primary: 13 },
    { composed: [] },
    { composed: [{ category: 'house', count: 8 }] },
    { composed: [{ category: 'house', count: 8 }, { category: 'house', count: 6 }] },
  ]) {
    assert.equal(evaluate(receipt(change)).accepted, false, JSON.stringify(change));
  }
});

test('unrequested, unsafe or overproduced categories cannot be called valid', () => {
  for (const composed of [
    [{ category: 'house', count: 8 }, { category: 'shell', count: 6 }],
    [{ category: 'house', count: 8 }, { category: 'npc', count: 7 }],
    [{ category: 'house', count: 14 }],
  ]) {
    assert.equal(evaluate(receipt({ composed })).accepted, false);
  }
  assert.equal(evaluate(receipt(), [
    { category: '../other', count: 8 }, { category: 'npc', count: 6 },
  ]).accepted, false);
});

test('clamped output is accepted only when mounted subset and totals are truthful', () => {
  const capped = receipt({
    composed: [{ category: 'house', count: 7 }],
    total: 9, primary: 7, variants: 2, clamped: true,
  });
  assert.deepEqual(evaluate(capped), {
    accepted: true, reason: null, count: 9, clamped: true,
  });
  assert.equal(evaluate({ ...capped, primary: 8 }).accepted, false);
  assert.equal(evaluate({ ...capped, clamped: false }).accepted, false);
});

test('unverified forge result cannot claim completion for a different game or request', () => {
  assert.equal(acceptSceneForgeResponse(true, receipt(), 'game-B', request).accepted, false);
  assert.equal(evaluate(receipt(), [{ category: 'tree', count: 14 }]).accepted, false);
  assert.equal(evaluate(receipt(), []).accepted, false);
});
