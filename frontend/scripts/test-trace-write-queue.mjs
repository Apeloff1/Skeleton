import assert from 'node:assert/strict';
import { test } from 'node:test';
import { LatestSnapshotWriter } from '../utils/LatestSnapshotWriter.ts';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

test('a stalled storage adapter holds only one active and one latest pending snapshot', async () => {
  const blocked = deferred();
  const written = [];
  const writer = new LatestSnapshotWriter(async snapshot => {
    written.push(snapshot);
    if (snapshot === 'first') await blocked.promise;
  });

  writer.enqueue('first');
  await Promise.resolve();
  assert.deepEqual(written, ['first']);
  for (let i = 0; i < 10_000; i++) writer.enqueue(`later-${i}`);
  assert.equal(writer.pendingCount, 2);
  blocked.resolve();
  await writer.pauseAndDiscard();
  assert.deepEqual(written, ['first']);
  writer.resume();
  assert.equal(writer.pendingCount, 0);
});

test('latest pending snapshot is written after a previous write settles', async () => {
  const blocked = deferred();
  const written = [];
  const writer = new LatestSnapshotWriter(async snapshot => {
    written.push(snapshot);
    if (snapshot === 'first') await blocked.promise;
  });
  writer.enqueue('first');
  await Promise.resolve();
  writer.enqueue('obsolete');
  writer.enqueue('latest');
  blocked.resolve();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(written, ['first', 'latest']);
  assert.equal(writer.pendingCount, 0);
});

test('write failures do not poison later snapshots', async () => {
  const written = [];
  const writer = new LatestSnapshotWriter(async snapshot => {
    written.push(snapshot);
    if (snapshot === 'fail') throw new Error('simulated native storage failure');
  });
  writer.enqueue('fail');
  await Promise.resolve();
  writer.enqueue('recovered');
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(written, ['fail', 'recovered']);
  assert.equal(writer.pendingCount, 0);
});

test('reset fence stops new enqueues until explicitly resumed', async () => {
  const written = [];
  const writer = new LatestSnapshotWriter(async snapshot => { written.push(snapshot); });
  await writer.pauseAndDiscard();
  writer.enqueue('discarded');
  assert.equal(writer.pendingCount, 0);
  writer.resume();
  writer.enqueue('allowed');
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(written, ['allowed']);
});
