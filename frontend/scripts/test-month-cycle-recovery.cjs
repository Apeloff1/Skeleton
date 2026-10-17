'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
function load(name, mocks = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../services', name), 'utf8');
  const output = ts.transpileModule(source, {
    fileName: name, compilerOptions: { module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020, esModuleInterop: true },
    reportDiagnostics: true,
  });
  assert.equal(output.diagnostics.length, 0);
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', output.outputText)(id => {
    assert.ok(Object.hasOwn(mocks, id), name + ': unexpected module ' + id);
    return mocks[id];
  }, mod, mod.exports);
  return mod.exports;
}
const { MonthCycleLedger } = load('monthCycleLedger.ts');
const { MonthCycleRecovery } = load('monthCycleRecovery.ts', {
  './monthCycleLedger': { MonthCycleLedger },
});
const START = 1_800_000_000_000, DAY = 86_400_000;
function storage() {
  const map = new Map();
  return { getItem: async k => map.get(k) ?? null,
    setItem: async (k, v) => { map.set(k, v); } };
}
async function start(count = 1) {
  const ledger = new MonthCycleLedger(storage(), 'account');
  for (let i = 0; i < count; i++)
    await ledger.enroll('job-' + i, 'view', 'build', START);
  return ledger;
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const controller = (ledger, worker, options = {}) =>
  new MonthCycleRecovery(ledger, worker, { clock: () => START, ...options });
test('a backend running state is persisted as observation, never completion', async () => {
  const ledger = await start();
  const recovery = controller(ledger, async () => ({ phase: 'running', cursor: 5 }));
  assert.deepEqual(await recovery.reconcileDue(), {
    attempted: 1, stillRunning: 1, disconnected: 0, terminalObserved: 0,
    skipped: 0, interrupted: false,
  });
  const row = (await ledger.inspect())[0];
  assert.equal(row.cursor, 5);
  assert.equal(row.status, 'observing');
  assert.equal(row.terminalState, null);
  assert.ok(row.nextCheckAt > START);
});
test('a second immediate resume pass makes no redundant backend calls', async () => {
  const ledger = await start();
  let calls = 0;
  const recovery = controller(ledger, async () => {
    calls++;
    return { phase: 'running' };
  });
  await recovery.reconcileDue();
  await recovery.reconcileDue();
  assert.equal(calls, 1);
});
test('explicit backend completion becomes terminal only after authoritative read', async () => {
  const ledger = await start();
  await controller(ledger, async () => ({ phase: 'completed', cursor: 17 })).reconcileDue();
  const row = (await ledger.inspect())[0];
  assert.equal(row.status, 'terminal_observed');
  assert.equal(row.terminalState, 'completed');
  assert.equal(row.cursor, 17);
  assert.deepEqual(await ledger.due(START + 100 * DAY), []);
});
test('disconnection retains an active job and schedules a finite retry', async () => {
  const ledger = await start();
  await controller(ledger, async () => { throw new Error('tunnel offline'); }).reconcileDue();
  const row = (await ledger.inspect())[0];
  assert.equal(row.status, 'disconnected');
  assert.equal(row.failures, 1);
  assert.equal(row.terminalState, null);
  assert.ok(row.nextCheckAt > START);
  assert.ok(row.nextCheckAt <= START + 7 * DAY);
});
test('retry time grows exponentially across distinct failed foreground passes', async () => {
  const ledger = await start();
  let now = START;
  const recovery = controller(ledger, async () => ({ phase: 'disconnected' }),
    { clock: () => now, baseRetryMs: 30_000, maxRetryMs: 24 * 60 * 60_000 });
  let lastDelay = 0;
  for (let n = 0; n < 5; n++) {
    await recovery.reconcileDue();
    const row = (await ledger.inspect())[0];
    const delay = row.nextCheckAt - now;
    assert.ok(delay >= lastDelay);
    lastDelay = delay;
    now = row.nextCheckAt;
  }
  assert.equal((await ledger.inspect())[0].failures, 5);
});
test('successful re-contact resets the disconnect streak and its next retry', async () => {
  const ledger = await start();
  let now = START;
  const recovery = controller(ledger, async row => ({
    phase: row.failures ? 'running' : 'disconnected',
  }), { clock: () => now });
  await recovery.reconcileDue();
  now = (await ledger.inspect())[0].nextCheckAt;
  await recovery.reconcileDue();
  const row = (await ledger.inspect())[0];
  assert.equal(row.status, 'observing');
  assert.equal(row.failures, 0);
});
test('observation concurrency respects one through four active jobs', async () => {
  const ledger = await start(10);
  let active = 0, peak = 0;
  const recovery = controller(ledger, async () => {
    active++; peak = Math.max(peak, active);
    await tick();
    active--;
    return { phase: 'running' };
  }, { maxConcurrent: 3 });
  const report = await recovery.reconcileDue();
  assert.equal(report.attempted, 10);
  assert.ok(peak <= 3 && peak >= 2);
});
test('recovery batch size caps scheduled work without deleting unattended jobs', async () => {
  const ledger = await start(30);
  let visited = 0;
  await controller(ledger, async () => {
    visited++;
    return { phase: 'running' };
  }, { batchSize: 5 }).reconcileDue();
  assert.equal(visited, 5);
  assert.equal((await ledger.inspect()).length, 30);
  assert.equal((await ledger.due(START)).length, 25);
});
test('concurrent resume commands share one in-flight reconciliation pass', async () => {
  const ledger = await start();
  let finish, calls = 0;
  const recovery = controller(ledger, async () => {
    calls++;
    return new Promise(resolve => { finish = resolve; });
  });
  const a = recovery.reconcileDue(), b = recovery.reconcileDue();
  assert.equal(a, b);
  await tick();
  finish({ phase: 'running' });
  await Promise.all([a,b]);
  assert.equal(calls, 1);
});
test('stopping a stalled network worker settles its client observation promptly', async () => {
  const ledger = await start();
  let arrived;
  const entered = new Promise(resolve => { arrived = resolve; });
  const recovery = controller(ledger, async () => {
    arrived();
    return new Promise(() => {});
  });
  const pass = recovery.reconcileDue();
  await entered;
  recovery.stop();
  const report = await pass;
  assert.equal(report.interrupted, true);
  assert.equal((await ledger.inspect())[0].status, 'observing');
});
test('non-cooperative transport has a strict observation deadline', async () => {
  const ledger = await start();
  const originalSet = global.setTimeout, originalClear = global.clearTimeout;
  global.setTimeout = (fn, ms) => {
    if (ms === 250) queueMicrotask(fn);
    return { id: 1 };
  };
  global.clearTimeout = () => {};
  try {
    const recovery = controller(ledger, () => new Promise(() => {}), { timeoutMs: 250 });
    const report = await recovery.reconcileDue();
    assert.equal(report.disconnected, 1);
  } finally {
    global.setTimeout = originalSet;
    global.clearTimeout = originalClear;
  }
});
test('a faulty projection callback cannot stop neighboring recovery workers', async () => {
  const ledger = await start(3);
  const recovery = controller(ledger, async () => ({ phase: 'running' }),
    { onObserved: () => { throw new Error('broken UI'); } });
  assert.equal((await recovery.reconcileDue()).stillRunning, 3);
});
test('month-old due receipts can be reconciled after process restart', async () => {
  const st = storage();
  const old = new MonthCycleLedger(st, 'account');
  await old.enroll('job-0', 'view', 'build', START);
  const restarted = new MonthCycleLedger(st, 'account');
  const day45 = START + 45 * DAY;
  const recovery = controller(restarted, async () => ({ phase: 'running' }),
    { clock: () => day45 });
  const result = await recovery.reconcileDue();
  assert.equal(result.stillRunning, 1);
  assert.equal((await restarted.inspect())[0].firstSeenAt, START);
});
test('high failure streaks saturate the retry cadence instead of overflowing', async () => {
  const ledger = await start();
  let now = START;
  const recovery = controller(ledger, async () => ({ phase: 'disconnected' }), {
    clock: () => now, baseRetryMs: 60_000, maxRetryMs: 12 * 60 * 60_000,
  });
  for (let i=0; i<30; i++) {
    await recovery.reconcileDue();
    const row = (await ledger.inspect())[0];
    assert.ok(row.nextCheckAt <= now + 7 * DAY);
    now = row.nextCheckAt;
  }
  assert.equal((await ledger.inspect())[0].failures, 30);
});
test('an explicit dismissed operation cannot be resurrected by a stale worker', async () => {
  const ledger = await start();
  let complete;
  const recovery = controller(ledger, () => new Promise(resolve => { complete = resolve; }));
  const pass = recovery.reconcileDue();
  await tick();
  const token = (await ledger.inspect())[0];
  await ledger.dismiss(token, START + 10);
  complete({ phase: 'completed' });
  await pass;
  assert.equal((await ledger.inspect())[0].status, 'dismissed');
});
test('one failed backend result does not block a neighboring due operation', async () => {
  const ledger = await start(2);
  const recovery = controller(ledger, async record => {
    if (record.operationId === 'job-0') throw new Error('bad backend');
    return { phase: 'completed' };
  }, { maxConcurrent: 2 });
  const report = await recovery.reconcileDue();
  assert.equal(report.disconnected, 1);
  assert.equal(report.terminalObserved, 1);
});
