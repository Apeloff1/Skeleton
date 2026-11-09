'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const Q = load('src/foundation/queryCache.ts');

function clock(start = 1000) { let t = start; const now = () => t; now.advance = (ms) => { t += ms; }; return now; }
const deferred = () => { let resolve, reject; const p = new Promise((a, b) => { resolve = a; reject = b; }); return { p, resolve, reject }; };

test('serializeKey and toError', () => {
  assert.equal(Q.serializeKey('a'), 'a');
  assert.equal(Q.serializeKey(['games', 1, null]), '["games",1,null]');
  assert.equal(Q.toError('x').message, 'x');
  assert.equal(Q.toError(42).message, 'Unexpected error');
  const e = new Error('y'); assert.equal(Q.toError(e), e);
});

test('fetch transitions loading -> success and notifies subscribers', async () => {
  const c = new Q.QueryCache(clock());
  const seen = [];
  c.subscribe('k', () => seen.push(c.get('k').status));
  assert.equal(c.get('k').status, 'idle');
  const v = await c.fetch('k', async () => [1, 2]);
  assert.deepEqual(v, [1, 2]);
  assert.deepEqual(seen, ['loading', 'success']);
  assert.equal(c.get('k').fetching, false);
});

test('concurrent fetches share one request', async () => {
  const c = new Q.QueryCache(clock());
  let calls = 0; const d = deferred();
  const a = c.fetch('k', () => { calls++; return d.p; });
  const b = c.fetch('k', () => { calls++; return d.p; });
  d.resolve('ok');
  assert.deepEqual(await Promise.all([a, b]), ['ok', 'ok']);
  assert.equal(calls, 1);
});

test('fresh data is reused within staleTime and refetched after', async () => {
  const now = clock(); const c = new Q.QueryCache(now);
  let calls = 0; const f = async () => ++calls;
  await c.fetch('k', f, { staleTimeMs: 100 });
  assert.equal(await c.fetch('k', f, { staleTimeMs: 100 }), 1);
  now.advance(100);
  assert.equal(await c.fetch('k', f, { staleTimeMs: 100 }), 2);
  assert.equal(await c.fetch('k', f, { staleTimeMs: 100, force: true }), 3);
});

test('errors keep last good data and are reported', async () => {
  const c = new Q.QueryCache(clock());
  await c.fetch('k', async () => ['a']);
  await assert.rejects(c.fetch('k', async () => { throw new Error('net'); }, { force: true }), /net/);
  const s = c.get('k');
  assert.equal(s.status, 'error');
  assert.deepEqual(s.data, ['a']);
  assert.equal(Q.viewStateOf(s), 'ready');
  const c2 = new Q.QueryCache(clock());
  await assert.rejects(c2.fetch('k', () => { throw 'sync'; }), /sync/);
  assert.equal(Q.viewStateOf(c2.get('k')), 'error');
});

test('invalidate drops stale in-flight results and marks data stale', async () => {
  const c = new Q.QueryCache(clock());
  const d = deferred();
  const p = c.fetch(['games', 1], () => d.p);
  c.invalidate(['games']);
  d.resolve('old');
  await p;
  assert.equal(c.get(['games', 1]).status, 'loading', 'stale result ignored');
  await c.fetch(['games', 1], async () => 'new');
  c.invalidate('["games"');
  assert.equal(c.isStale(['games', 1], 1e9), true);
  await c.fetch('other', async () => 1);
  c.invalidate(['games']);
  assert.equal(c.isStale('other', 1e9), false);
});

test('setData, clear and bounded eviction', async () => {
  const c = new Q.QueryCache(clock(), 3);
  c.setData('a', 1);
  assert.equal(c.get('a').data, 1);
  for (const k of ['b', 'c', 'd', 'e']) await c.fetch(k, async () => k);
  assert.ok(c.size() <= 3);
  const unsub = c.subscribe('keep', () => {});
  for (const k of ['f', 'g', 'h']) await c.fetch(k, async () => k);
  assert.ok(c.size() <= 4);
  unsub();
  c.clear();
  assert.equal(c.get('h').status, 'idle');
});

test('viewStateOf / defaultIsEmpty', () => {
  const ok = (data) => ({ status: 'success', data, error: null, updatedAt: 1, fetching: false });
  assert.equal(Q.viewStateOf({ status: 'idle', data: undefined, error: null, updatedAt: 0, fetching: false }), 'loading');
  assert.equal(Q.viewStateOf(ok([])), 'empty');
  assert.equal(Q.viewStateOf(ok({ items: [] })), 'empty');
  assert.equal(Q.viewStateOf(ok({ items: [1] })), 'ready');
  assert.equal(Q.viewStateOf(ok(0)), 'ready');
  assert.equal(Q.viewStateOf(ok(null)), 'empty');
  assert.equal(Q.viewStateOf(ok([1]), () => true), 'empty');
});
