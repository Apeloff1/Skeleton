import assert from 'node:assert/strict';
import { test } from 'node:test';
import { OrderedCommitQueue } from '../src/utils/OrderedCommitQueue.ts';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((r, j) => { resolve = r; reject = j; });
  return { promise, resolve, reject };
}

test('late crash increment cannot overwrite a clean acknowledgement', async () => {
  const stalled = deferred();
  const writes = [];
  let durable = '0';
  const queue = new OrderedCommitQueue();
  const increment = queue.enqueue(async () => {
    await stalled.promise;
    durable = '1';
    writes.push('crash:1');
  });
  const clean = queue.enqueue(async () => {
    durable = '0';
    writes.push('clean:0');
  });
  await Promise.resolve();
  assert.equal(durable, '0');
  stalled.resolve();
  await Promise.all([increment, clean, queue.drain()]);
  assert.deepEqual(writes, ['crash:1', 'clean:0']);
  assert.equal(durable, '0');
});

test('a rejected native write does not prevent clean recovery acknowledgement', async () => {
  const queue = new OrderedCommitQueue();
  const fail = queue.enqueue(async () => { throw new Error('storage locked'); });
  const clean = queue.enqueue(async () => 'persisted');
  await assert.rejects(fail, /storage locked/);
  assert.equal(await clean, 'persisted');
  await queue.drain();
});

test('drain remains pending while an old native write has not acknowledged', async () => {
  const stalled = deferred();
  const queue = new OrderedCommitQueue();
  queue.enqueue(async () => stalled.promise);
  let drained = false;
  void queue.drain().then(() => { drained = true; });
  await Promise.resolve();
  assert.equal(drained, false);
  stalled.resolve();
  await queue.drain();
  assert.equal(drained, true);
});
