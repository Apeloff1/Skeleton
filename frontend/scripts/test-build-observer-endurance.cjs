'use strict';
const { compileFunction } = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const src = fs.readFileSync(path.join(__dirname, '../src/product/buildJobLifecycle.ts'), 'utf8');
const compiled = ts.transpileModule(src, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true,
}, reportDiagnostics: true });
assert.equal(compiled.diagnostics.length, 0);
const mod = { exports: {} };
compileFunction(compiled.outputText, ['require', 'module', 'exports'])(require, mod, mod.exports);
const { classifyBuildJob, watchBuildJob } = mod.exports;

test('known backend states classify terminal truth without accepting unknown as complete', () => {
  assert.equal(classifyBuildJob({ state: 'RUNNING' }), 'pending');
  assert.equal(classifyBuildJob({ data: { status: 'done' } }), 'completed');
  assert.equal(classifyBuildJob({ status: 'success', error: 'failed artifact' }), 'failed');
  assert.equal(classifyBuildJob({ job_status: 'canceled' }), 'cancelled');
  assert.equal(classifyBuildJob({ status: 'thinking' }), 'pending');
  assert.equal(classifyBuildJob(null), 'pending');
});

test('a single transient failure does not mark the backend job failed', async () => {
  let calls = 0;
  const out = await watchBuildJob(async () => {
    if (++calls === 1) throw new Error('wifi handoff');
    return { status: 'completed' };
  }, { intervalMs: 100, maxChecks: 3 });
  assert.equal(out.phase, 'completed');
  assert.equal(out.checks, 2);
});

test('repeated failed status reads end in disconnected, not false build failure', async () => {
  const out = await watchBuildJob(async () => { throw new Error('no tunnel'); },
    { maxConsecutiveErrors: 2, intervalMs: 100, maxChecks: 8 });
  assert.equal(out.phase, 'disconnected');
  assert.equal(out.checks, 2);
  assert.match(out.message, /may still be running/);
});

test('explicit backend build failure is not hidden behind transport retries', async () => {
  const out = await watchBuildJob(async () => ({ status: 'failed' }), { maxChecks: 100 });
  assert.equal(out.phase, 'failed');
  assert.equal(out.checks, 1);
});

test('caller-provided maxChecks is an observation cap, not backend cancellation', async () => {
  let checks = 0;
  const out = await watchBuildJob(async () => {
    checks++;
    return { state: 'running' };
  }, { maxChecks: 1 });
  assert.equal(out.phase, 'timeout');
  assert.equal(checks, 1);
  assert.match(out.message, /may still be running/);
});

test('poll callback failures do not kill live monitoring', async () => {
  let checks = 0;
  const out = await watchBuildJob(async () => ({ status: ++checks >= 2 ? 'done' : 'running' }),
    { intervalMs: 100, onPending: () => { throw new Error('broken progress view'); } });
  assert.equal(out.phase, 'completed');
});

test('monitoring an already-aborted observation never contacts the backend', async () => {
  const c = new AbortController();
  c.abort();
  let calls = 0;
  const out = await watchBuildJob(async () => { calls++; return { status: 'done' }; },
    { signal: c.signal });
  assert.equal(out.phase, 'aborted');
  assert.equal(calls, 0);
});

test('aborting a noncooperative hung request settles without cancelling the job', async () => {
  const c = new AbortController();
  let entered;
  const triggered = new Promise(resolve => { entered = resolve; });
  const job = watchBuildJob(() => { entered(); return new Promise(() => {}); },
    { signal: c.signal });
  await triggered;
  c.abort();
  const out = await job;
  assert.equal(out.phase, 'aborted');
  assert.equal(out.checks, 0);
  assert.match(out.message, /not cancelled/);
});

test('request deadline terminates a stuck transport without an infinite wait', async () => {
  const oldSet = global.setTimeout;
  const oldClear = global.clearTimeout;
  global.setTimeout = (fn, ms) => {
    if (ms === 250) queueMicrotask(fn);
    return { fake: true };
  };
  global.clearTimeout = () => {};
  try {
    const out = await watchBuildJob(() => new Promise(() => {}),
      { requestTimeoutMs: 250, maxConsecutiveErrors: 1 });
    assert.equal(out.phase, 'disconnected');
  } finally {
    global.setTimeout = oldSet;
    global.clearTimeout = oldClear;
  }
});

test('long idle watches adapt cadence but do not expire arbitrarily', async () => {
  let checks = 0;
  const delays = [];
  const oldSet = global.setTimeout;
  const oldClear = global.clearTimeout;
  global.setTimeout = (fn, ms) => {
    if (ms < 1000) { delays.push(ms); queueMicrotask(fn); }
    return { fake: true };
  };
  global.clearTimeout = () => {};
  try {
    const out = await watchBuildJob(async () => ({
      state: ++checks < 8 ? 'running' : 'success',
    }), { intervalMs: 100, maxIntervalMs: 380 });
    assert.equal(out.phase, 'completed');
    assert.equal(out.checks, 8);
    assert.deepEqual(delays, [100, 200, 380, 380, 380, 380, 380]);
  } finally {
    global.setTimeout = oldSet;
    global.clearTimeout = oldClear;
  }
});

test('malformed poll options resolve to finite safe defaults', async () => {
  const out = await watchBuildJob(async () => ({ status: 'complete' }), {
    intervalMs: Infinity, requestTimeoutMs: Number.NaN,
    maxChecks: -100, maxConsecutiveErrors: Number.NaN,
  });
  assert.equal(out.phase, 'completed');
  assert.equal(out.checks, 1);
});

test('job cancellation response only reports cancelled when backend says so', async () => {
  const out = await watchBuildJob(async () => ({ data: { status: 'cancelled' } }));
  assert.equal(out.phase, 'cancelled');
  assert.equal(out.checks, 1);
});
