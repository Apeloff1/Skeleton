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
test('backend disconnect is recoverable failure, not a hanging spinner', async () => {
  const r = await watchBuildJob(async () => { throw Error('secret'); }, { maxChecks: 2, intervalMs: 0 });
  assert.equal(r.phase, 'failed');
  assert.equal(r.message.includes('secret'), false);
});
