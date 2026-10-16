import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MAX_NATIVE_MUTATION_KEYS, NativeMutationFence } from '../utils/NativeMutationFence.ts';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((r, j) => { resolve = r; reject = j; });
  return { promise, resolve, reject };
}

test('timed-out native write retains exclusive ownership until it actually settles', async () => {
  const storage = new Map();
  const stalled = deferred();
  const gate = new NativeMutationFence();
  let calls = 0;
  const first = gate.run(['project:1'], async () => {
    calls++;
    await stalled.promise;
    storage.set('project:1', 'old');
  });
  await Promise.resolve();
  assert.equal(gate.isBusy('project:1'), true);
  for (let i = 0; i < 10_000; i++) {
    assert.equal(await gate.run(['project:1'], async () => {
      calls++;
      storage.set('project:1', 'new');
    }), false);
  }
  assert.equal(calls, 1, 'never create a zombie write backlog');
  stalled.resolve();
  assert.equal(await first, true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(await gate.run(['project:1'], async () => {
    calls++;
    storage.set('project:1', 'new');
  }), true);
  assert.equal(storage.get('project:1'), 'new');
  assert.equal(calls, 2);
});

test('independent project keys remain parallel, multi-key deletion excludes overlap', async () => {
  const stalled = deferred();
  const gate = new NativeMutationFence();
  const first = gate.run(['world:A'], async () => stalled.promise);
  const second = gate.run(['world:B'], async () => undefined);
  assert.equal(await second, true);
  assert.equal(await gate.run(['world:A', 'world:B'], async () => undefined), false);
  stalled.resolve();
  assert.equal(await first, true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(await gate.run(['world:A', 'world:B'], async () => undefined), true);
});

test('native rejection releases key ownership for operator retry', async () => {
  const gate = new NativeMutationFence();
  const failed = await gate.run(['asset:1'], async () => { throw Error('device locked'); });
  assert.equal(failed, false);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(gate.isBusy('asset:1'), false);
  assert.equal(await gate.run(['asset:1'], async () => undefined), true);
});

test('native-stall admission has a fixed global ceiling', async () => {
  const stalled = deferred();
  const gate = new NativeMutationFence();
  const active = gate.run(
    Array.from({ length: MAX_NATIVE_MUTATION_KEYS }, (_, i) => `scratch:${i}`),
    async () => stalled.promise,
  );
  assert.equal(gate.inFlight, 1);
  assert.equal(await gate.run(['project:new'], async () => undefined), false);
  assert.equal(await gate.run(
    Array.from({ length: MAX_NATIVE_MUTATION_KEYS + 1 }, (_, i) => `too-many:${i}`),
    async () => undefined,
  ), false);
  stalled.resolve();
  assert.equal(await active, true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(await gate.run(['project:new'], async () => undefined), true);
});
