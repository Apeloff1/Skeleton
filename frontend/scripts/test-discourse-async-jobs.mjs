import { readFileSync } from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  submitDiscourseJob, pollDiscourseJob, MAX_DISCOURSE_WAIT_MS,
} from '../src/features/discourse/discourseJob.ts';

const JOB_ID = 'ab'.repeat(16);
const payload = {
  task: 'creative', prompt: 'Create a unique puzzle mechanic', discord: false,
};
function ok(data) {
  return { ok: true, status: 200, data, error: null };
}
function terminal(extra = {}) {
  return {
    status: 'done', job_id: JOB_ID,
    winner_index: 0, winner_model: 'local:gguf',
    winner_content: 'A coherent original light puzzle mechanic.',
    winner_score: 87, judge_model: 'local:gguf',
    judge_status: 'self_scored',
    deliberation_mode: 'single_model_self_review',
    selection_source: 'tenant_model_inventory',
    panel: ['local:gguf'],
    candidates: [{ model: 'local:gguf', content: 'A coherent original light puzzle mechanic.' }],
    ...extra,
  };
}
function mockTransport({ post, get }) {
  return {
    post: async (...args) => post(...args),
    get: async (...args) => get(...args),
  };
}

test('submits once and observes a confirmed terminal result without a duplicate POST', async () => {
  const calls = { post: 0, get: 0 };
  const statuses = [];
  const transport = mockTransport({
    post: async (path, body, opts) => {
      calls.post++;
      assert.equal(path, '/api/discourse/deliberate/async');
      assert.deepEqual(body, payload);
      assert.equal(opts.retries, 0);
      return ok({ status: 'running', job_id: JOB_ID });
    },
    get: async (path, opts) => {
      calls.get++;
      assert.equal(path, '/api/discourse/result/' + JOB_ID);
      assert.equal(opts.retries, 0);
      return ok(calls.get === 1 ? { status: 'running' } : terminal());
    },
  });
  const outcome = await submitDiscourseJob(transport, payload, {
    pollIntervalMs: 10, maxWaitMs: 2000,
    onProgress: progress => statuses.push(progress.status),
  });
  assert.equal(outcome.ok, true);
  assert.equal(outcome.jobId, JOB_ID);
  assert.equal(outcome.result?.deliberation_mode, 'single_model_self_review');
  assert.deepEqual(calls, { post: 1, get: 2 });
  assert.deepEqual(statuses, ['submitting', 'running', 'running']);
});

test('connection loss during POST does not silently resubmit paid model work', async () => {
  let count = 0;
  const transport = mockTransport({
    post: async () => {
      count++;
      throw Error('sensitive-transport-internals');
    },
    get: async () => { throw Error('must not poll without job receipt'); },
  });
  const outcome = await submitDiscourseJob(transport, payload);
  assert.deepEqual(outcome, {
    ok: false, jobId: null,
    error: 'admission_unconfirmed_do_not_retry', recoverable: false,
  });
  assert.equal(count, 1);
  assert.equal(JSON.stringify(outcome).includes('sensitive-transport'), false);
});

test('untrusted job IDs are rejected before any network activity', async () => {
  const transport = mockTransport({
    post: async () => { throw Error('unexpected POST'); },
    get: async () => { throw Error('unexpected GET'); },
  });
  for (const bad of ['../other', 'A'.repeat(32), 'g'.repeat(32), '', JOB_ID + '?']) {
    const outcome = await pollDiscourseJob(transport, bad);
    assert.equal(outcome.ok, false);
    assert.equal(outcome.error, 'invalid_job_receipt');
  }
});

test('known job can be re-observed without submitting another job', async () => {
  const transport = mockTransport({
    post: async () => { throw Error('recovery must not start another job'); },
    get: async () => ok(terminal()),
  });
  const observed = await pollDiscourseJob(transport, JOB_ID);
  assert.equal(observed.ok, true);
});

test('authentication denial is terminal rather than retried', async () => {
  let calls = 0;
  const transport = mockTransport({
    post: async () => { throw Error('unexpected POST'); },
    get: async () => { calls++; return { ok: false, status: 401, data: null, error: 'Unauthorized' }; },
  });
  const outcome = await pollDiscourseJob(transport, JOB_ID, { pollIntervalMs: 10 });
  assert.equal(outcome.ok, false);
  assert.equal(outcome.error, 'Unauthorized');
  assert.equal(outcome.recoverable, false);
  assert.equal(calls, 1);
});

test('bounded transient retry recovers an existing job', async () => {
  let gets = 0;
  const transport = mockTransport({
    post: async () => { throw Error('unexpected POST'); },
    get: async () => {
      gets++;
      return gets <= 2 ? { ok: false, status: 503, data: null, error: 'offline' } : ok(terminal());
    },
  });
  const outcome = await pollDiscourseJob(transport, JOB_ID, { pollIntervalMs: 10, maxWaitMs: 1500 });
  assert.equal(outcome.ok, true);
  assert.equal(gets, 3);
});

test('transient outages stop after bounded retry count, preserving the receipt', async () => {
  let gets = 0;
  const transport = mockTransport({
    post: async () => { throw Error('unexpected POST'); },
    get: async () => {
      gets++;
      return { ok: false, status: 503, data: null, error: 'offline' };
    },
  });
  const outcome = await pollDiscourseJob(transport, JOB_ID, { pollIntervalMs: 10, maxWaitMs: 1500 });
  assert.equal(outcome.ok, false);
  assert.equal(outcome.error, 'job_observation_temporarily_unavailable');
  assert.equal(outcome.recoverable, true);
  assert.equal(outcome.jobId, JOB_ID);
  assert.equal(gets, 4);
});

test('stop observing aborts polling without asserting the admitted job was cancelled', async () => {
  const abort = new AbortController();
  const transport = mockTransport({
    post: async () => { throw Error('unexpected POST'); },
    get: async () => ok({ status: 'running' }),
  });
  const work = pollDiscourseJob(transport, JOB_ID, {
    signal: abort.signal, pollIntervalMs: 1000, maxWaitMs: 2000,
  });
  setTimeout(() => abort.abort(), 5);
  const outcome = await work;
  assert.equal(outcome.ok, false);
  assert.equal(outcome.error, 'observation_cancelled');
  assert.equal(outcome.recoverable, true);
  assert.equal(outcome.jobId, JOB_ID);
});

test('malformed terminal receipts cannot masquerade as a winner', async () => {
  const invalid = [
    terminal({ winner_index: true }),
    terminal({ winner_index: 8 }),
    terminal({ winner_model: 'other:model' }),
    terminal({ candidates: [] }),
    terminal({ winner_content: '' }),
    terminal({ panel: ['local:gguf', 42] }),
  ];
  for (const rec of invalid) {
    const transport = mockTransport({
      post: async () => { throw Error('unexpected POST'); },
      get: async () => ok(rec),
    });
    const outcome = await pollDiscourseJob(transport, JOB_ID);
    assert.equal(outcome.ok, false);
    assert.equal(outcome.error, 'invalid_terminal_result');
  }
});

test('failed terminal job is never represented as completed', async () => {
  const transport = mockTransport({
    post: async () => { throw Error('unexpected POST'); },
    get: async () => ok({ status: 'error', error: 'deliberation_not_durable' }),
  });
  const outcome = await pollDiscourseJob(transport, JOB_ID);
  assert.equal(outcome.ok, false);
  assert.equal(outcome.error, 'deliberation_not_durable');
});

test('backend must return a bounded acknowledged job admission receipt', async () => {
  const transport = mockTransport({
    post: async () => ok({ status: 'running', job_id: '../../../secret' }),
    get: async () => { throw Error('should not poll malformed receipt'); },
  });
  const outcome = await submitDiscourseJob(transport, payload);
  assert.equal(outcome.error, 'invalid_admission_receipt');
});

test('observation is finite even when the server stays running', async () => {
  const transport = mockTransport({
    post: async () => { throw Error('unexpected POST'); },
    get: async () => ok({ status: 'running' }),
  });
  const outcome = await pollDiscourseJob(transport, JOB_ID, {
    maxWaitMs: 100, pollIntervalMs: 10,
  });
  assert.equal(outcome.ok, false);
  assert.equal(outcome.error, 'job_observation_timeout');
  assert.equal(outcome.recoverable, true);
  assert.equal(MAX_DISCOURSE_WAIT_MS, 240000);
});


test('the UI uses bounded asynchronous jobs and never a long synchronous request', () => {
  const source = readFileSync(new URL('../app/discourse.tsx', import.meta.url), 'utf8');
  assert.match(source, /submitDiscourseJob\(api,/);
  assert.match(source, /pollDiscourseJob\(api,/);
  assert.match(source, /observer\.current\?\.abort\(\)/);
  assert.match(source, /Stop observing \(job may continue\)/);
  assert.doesNotMatch(source, /api\.post.*'\/api\/discourse\/deliberate'[\s,]/);
});
