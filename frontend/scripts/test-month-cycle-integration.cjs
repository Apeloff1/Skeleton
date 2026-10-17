'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
function load(file, mocks = {}) {
  const code = fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
  const output = ts.transpileModule(code, { fileName: file,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      esModuleInterop: true }, reportDiagnostics: true });
  assert.equal(output.diagnostics.length, 0, file);
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', output.outputText)(id => {
    assert.ok(Object.hasOwn(mocks, id), file + ': unexpected import ' + id);
    return mocks[id];
  }, mod, mod.exports);
  return mod.exports;
}
const ledgerModule = load('services/monthCycleLedger.ts');
const { MonthCycleLedger } = ledgerModule;
const recoveryModule = load('services/monthCycleRecovery.ts', {
  './monthCycleLedger': ledgerModule,
});
const lifecycle = load('src/product/buildJobLifecycle.ts');
const { buildCycleWorker } = load('services/monthCycleBuildAdapter.ts', {
  '../src/product/buildJobLifecycle': lifecycle,
});
const studioModule = load('services/monthCycleStudioAdapter.ts', {
  '../src/product/gameStudioAgentClient': { getStudioGoal: async () => {
    throw new Error('use injected fake');
  } },
});
const reducer = load('services/operationStreamReducer.ts');
const { OperationBrowserSession } = load('services/operationStreamSession.ts', {
  './operationStreamReducer.ts': reducer,
});
function storage() {
  const map = new Map();
  return { getItem: async key => map.get(key) ?? null,
    setItem: async (key, value) => { map.set(key, value); } };
}
function app(t) {
  const cursor = {
    load: async () => 0, save: async () => {}, clear: async () => {},
  };
  return new OperationBrowserSession('op-1', {
    replay: t, acknowledge: async () => ({ ok: true }),
    resync: async () => null, cancel: async () => ({ ok: true }),
  }, cursor, { consumerId: 'desktop' });
}
function payload(state = 'running') {
  return { ok: true, payload: {
    ok: true,
    operation: { operation_id: 'op-1', state },
    events: [], after_sequence: 0, latest_sequence: 0,
    stream_latest_sequence: 0, has_more: false,
    terminal: state !== 'running',
    canonical_result: state !== 'running'
      ? { status: state, final_output: 'confirmed' } : null,
  } };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
test('resumable stream registers durable identity before any network response', async () => {
  const ledger = new MonthCycleLedger(storage(), 'alice');
  let respond;
  const session = app(() => new Promise(resolve => { respond = resolve; }));
  const pending = session.resumeDurable(ledger);
  for (let i=0;i<5 && !respond;i++) await tick();
  assert.ok(respond, 'network request should have been issued');
  const rows = await ledger.inspect();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].operationId, 'op-1');
  assert.equal(rows[0].consumerId, 'desktop');
  respond(payload());
  await pending;
});
test('successful canonical replay is recorded as active but not terminal', async () => {
  const ledger = new MonthCycleLedger(storage(), 'alice');
  const state = await app(async () => payload()).resumeDurable(ledger);
  assert.equal(state.terminal, false);
  const receipt = (await ledger.inspect())[0];
  assert.equal(receipt.status, 'observing');
  assert.equal(receipt.terminalState, null);
});
test('authoritative completed canonical result creates terminal observation', async () => {
  const ledger = new MonthCycleLedger(storage(), 'alice');
  const state = await app(async () => payload('completed')).resumeDurable(ledger);
  assert.equal(state.terminal, true);
  const record = (await ledger.inspect())[0];
  assert.equal(record.status, 'terminal_observed');
  assert.equal(record.terminalState, 'completed');
});
test('transport disconnect is not treated as failed backend operation', async () => {
  const ledger = new MonthCycleLedger(storage(), 'alice');
  await app(async () => { throw new Error('router offline'); }).resumeDurable(ledger);
  const record = (await ledger.inspect())[0];
  assert.equal(record.status, 'disconnected');
  assert.equal(record.terminalState, null);
});
test('opening a previously terminal stream does not replay or relaunch it', async () => {
  const ledger = new MonthCycleLedger(storage(), 'alice');
  const saved = await ledger.enroll('op-1', 'desktop', 'operation');
  await ledger.observe(saved, { phase: 'terminal_observed',
    terminalState: 'completed' });
  let queries = 0;
  await app(async () => { queries++; return payload(); }).resumeDurable(ledger);
  assert.equal(queries, 0);
});
test('studio goal is not reported completed without verified completion receipt', () => {
  const classify = studioModule.classifyStudioGoalObservation;
  assert.equal(classify({ status: 'completed', completion: { verified: false } }), 'running');
  assert.equal(classify({ status: 'completed' }), 'running');
  assert.equal(classify({ status: 'completed', completion: { verified: true } }), 'completed');
});
test('studio terminal failures and cancellation rely on backend state', () => {
  const classify = studioModule.classifyStudioGoalObservation;
  assert.equal(classify({ status: 'failed' }), 'failed');
  assert.equal(classify({ status: 'cancelled' }), 'cancelled');
  assert.equal(classify({ status: 'waiting_approval' }), 'running');
});
test('studio worker is read-only and forwards authoritative cursor', async () => {
  const worker = studioModule.studioGoalCycleWorker(async id => {
    assert.equal(id, 'goal-1');
    return { status: 'running', cursor: 81 };
  });
  const row = { operationId: 'goal-1' };
  assert.deepEqual(await worker(row, new AbortController().signal),
    { phase: 'running', cursor: 81 });
});
test('studio invalid server cursors cannot be recorded as verified progress', async () => {
  const worker = studioModule.studioGoalCycleWorker(async () =>
    ({ status: 'running', cursor: Infinity }));
  await assert.rejects(worker({ operationId: 'goal-1' }, new AbortController().signal),
    /cursor/);
});
test('studio registration is idempotent and preserves the backend goal ID', async () => {
  const ledger = new MonthCycleLedger(storage(), 'alice');
  const first = await studioModule.registerStudioGoalCycle(
    ledger, { goal_id: 'goal-1', status: 'running' }, 'ui');
  const second = await studioModule.registerStudioGoalCycle(
    ledger, { goal_id: 'goal-1', status: 'running' }, 'ui');
  assert.equal(first.incarnation, second.incarnation);
  assert.equal((await ledger.inspect()).length, 1);
});
test('build status adapter reports pending as active observation', async () => {
  const worker = buildCycleWorker(async () => ({ status: 'running' }));
  const result = await worker({ operationId: 'game-build-1' }, new AbortController().signal);
  assert.deepEqual(result, { phase: 'running' });
});
test('build status adapter records only authoritative completed results', async () => {
  const worker = buildCycleWorker(async () => ({ status: 'completed' }));
  assert.deepEqual(await worker({ operationId: 'job' }, new AbortController().signal),
    { phase: 'completed' });
});
test('build status adapter returns disconnected after failed read', async () => {
  const worker = buildCycleWorker(async () => { throw new Error('offline'); });
  assert.deepEqual(await worker({ operationId: 'job' }, new AbortController().signal),
    { phase: 'disconnected' });
});
test('build status adapter does not send mutations to resume the backend job', async () => {
  let calls = 0;
  const worker = buildCycleWorker(async (_job, signal) => {
    assert.equal(signal instanceof AbortSignal, true);
    calls++;
    return { status: 'queued' };
  });
  await worker({ operationId: 'job' }, new AbortController().signal);
  assert.equal(calls, 1);
});
