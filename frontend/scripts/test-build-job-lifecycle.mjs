import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyBuildJob, watchBuildJob } from '../src/product/buildJobLifecycle.ts';

test('queued, waiting, running, retrying and unknown are never success', () => {
  for (const status of ['queued', 'waiting', 'running', 'retrying', 'pending', 'wat', '']) {
    assert.equal(classifyBuildJob({ data: { job_status: status } }), 'pending');
  }
});
test('terminal statuses distinguish completion, cancellation and errors', () => {
  assert.equal(classifyBuildJob({ data: { job_status: 'done', ok: true } }), 'completed');
  assert.equal(classifyBuildJob({ data: { status: 'completed' } }), 'completed');
  assert.equal(classifyBuildJob({ data: { job_status: 'done', ok: false } }), 'failed');
  assert.equal(classifyBuildJob({ data: { job_status: 'error' } }), 'failed');
  assert.equal(classifyBuildJob({ data: { status: 'cancelled' } }), 'cancelled');
});
const custody = (patch = {}) => ({ runner_live: false, physical_workers: 0, stop_requested: false,
  drain_pending: false, partial_artifacts: true, storage_failed: false, unflushed_files: 0, ...patch });
test('physical work retains custody despite a terminal label', () => {
  for (const status of ['completed', 'failed', 'cancelled']) {
    for (const execution of [custody({ runner_live: true }), custody({ physical_workers: 1 }), custody({ drain_pending: true })]) {
      assert.equal(classifyBuildJob({ status, execution }), 'pending', `${status} must wait for physical drain`);
    }
  }
});
test('success requires stopped work and durable output; retained artifact presence is valid', () => {
  assert.equal(classifyBuildJob({ status: 'completed', execution: custody() }), 'completed');
  for (const patch of [{ stop_requested: true }, { storage_failed: true }, { unflushed_files: 3 }]) {
    assert.equal(classifyBuildJob({ status: 'completed', execution: custody(patch) }), 'pending');
  }
  assert.equal(classifyBuildJob({ status: 'cancelled', execution: custody({ stop_requested: true, unflushed_files: 3 }) }), 'cancelled');
  assert.equal(classifyBuildJob({ status: 'failed', execution: custody({ storage_failed: true, unflushed_files: 3 }) }), 'failed');
});
test('malformed physical custody cannot unlock success', () => {
  for (const execution of [null, [], {}, custody({ runner_live: 'false' }), custody({ physical_workers: -1 }),
    custody({ physical_workers: 1.5 }), custody({ unflushed_files: Infinity }), custody({ storage_failed: undefined })]) {
    assert.equal(classifyBuildJob({ status: 'completed', execution }), 'pending');
  }
});
test('waiter polls sequentially and stops only at a terminal outcome', async () => {
  let calls = 0;
  const result = await watchBuildJob(async () => {
    calls += 1;
    return { data: { job_status: ['queued','running','done'][calls-1] } };
  }, { intervalMs: 0, maxChecks: 10 });
  assert.equal(result.phase, 'completed');
  assert.equal(calls, 3);
});
test('waiter has a finite observation limit without inventing success', async () => {
  const r = await watchBuildJob(async () => ({ data: { status: 'running' } }), { intervalMs: 0, maxChecks: 2 });
  assert.equal(r.phase, 'timeout');
  assert.equal(r.checks, 2);
});
test('abort prevents future fetches and does not claim backend cancellation', async () => {
  const controller = new AbortController();
  let count = 0;
  const p = watchBuildJob(async () => {
    count += 1;
    controller.abort();
    return { data: { status: 'done' } };
  }, { signal: controller.signal, maxChecks: 3, intervalMs: 0 });
  assert.equal((await p).phase, 'aborted');
  assert.equal(count, 1);
});
test('backend disconnect is recoverable, not a failure claim or a hanging spinner', async () => {
  // A rejected status read is not evidence the build failed (see buildJobLifecycle.ts).
  const r = await watchBuildJob(async () => { throw Error('secret'); }, { maxChecks: 5, intervalMs: 0, maxConsecutiveErrors: 2 });
  assert.equal(r.phase, 'disconnected');
  assert.equal(r.message.includes('secret'), false);
});
