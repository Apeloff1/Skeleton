'use strict';
// Real retention helper + canonical queue; no backend, generation or replay.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function load(file, imports) {
  const compiled = ts.transpileModule(fs.readFileSync(path.join(ROOT, file), 'utf8'), {
    fileName: file, reportDiagnostics: true, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  assert.equal(compiled.diagnostics.length, 0);
  const module = { exports: {} };
  compileFunction(compiled.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), file + ': unexpected integration ' + id); return imports[id];
  }, module, module.exports);
  return module.exports;
}
const queue = load('src/utils/OrderedCommitQueue.ts', {});
const lifecycle = load('src/product/buildJobLifecycle.ts', {});
function fixture() {
  let epoch = 0, principalId = 'creator+one@example.test', tenantId = 'tenant:one';
  const rows = new Map(), calls = [], observers = new Set();
  const wire = {
    identity: async () => ({ tenantId, principalId }),
    get: async key => rows.get(key) ?? null,
    set: async (key, value) => { rows.set(key, value); },
    remove: async key => { rows.delete(key); },
  };
  const storage = { getItem: async key => { calls.push({ kind: 'get', key }); return wire.get(key); },
    setItem: async (key, value) => { calls.push({ kind: 'set', key, value }); return wire.set(key, value); },
    removeItem: async key => { calls.push({ kind: 'remove', key }); return wire.remove(key); } };
  const owner = { getAuthEpoch: () => epoch, resolveStorageTenantIdentity: () => wire.identity(),
    subscribeAuthChanges(fn) { observers.add(fn); return () => observers.delete(fn); } };
  const imports = { '@react-native-async-storage/async-storage': { __esModule: true, default: storage },
    '../auth/gameforgeAuth': owner, '../utils/OrderedCommitQueue': queue };
  const reload = () => load('src/product/playableJobObservation.ts', imports);
  return { ...reload(), reload, rows, calls, wire, observers,
    change(next = 'creator+two@example.test', tenant = tenantId) { principalId = next; tenantId = tenant; epoch++; for (const fn of observers) fn(); } };
}
const retained = { jobId: 'job-original-1', kind: 'generate', engineRequestKey: 'engine-chat:original:1', errorCode: 'project_model_execution_unconfirmed' };

test('retention round-trips the exact original job and bounded metadata after a module reload', async () => {
  const f = fixture(), store = await f.openPlayableJobObservation();
  await store.set(retained); assert.deepEqual(await store.get(), retained);
  const key = [...f.rows.keys()][0]; assert.equal(key, 'playable-job-observation:v1:tenant%3Aone:creator%2Bone%40example.test');
  assert.deepEqual(JSON.parse(f.rows.get(key)), { schema_version: 1, record: retained });
  store.dispose(); const restored = await f.reload().openPlayableJobObservation();
  assert.deepEqual(await restored.get(), retained); assert.equal(await restored.clear(retained.jobId), true);
  assert.equal(await restored.get(), null); restored.dispose(); assert.equal(f.observers.size, 0);
});

test('a retained record is a validated metadata snapshot, never prompts, tokens or a mutable caller object', async () => {
  const f = fixture(), store = await f.openPlayableJobObservation();
  for (const value of [null, {}, { jobId: 42 }, { jobId: '../job' }, { jobId: 'x'.repeat(129) },
    { jobId: 'job', prompt: 'private prompt' }, { jobId: 'job', token: 'secret' },
    { jobId: 'job', engineRequestKey: 'x'.repeat(257) }, { jobId: 'job', errorCode: 'new\nline' },
    { jobId: 'job', kind: 'x'.repeat(65) }]) await assert.rejects(store.set(value));
  assert.equal(f.calls.length, 0);
  const mutable = { ...retained }, saving = store.set(mutable); mutable.jobId = 'job-other'; mutable.errorCode = 'altered'; await saving;
  assert.deepEqual(await store.get(), retained); store.dispose();
});

test('receipt acknowledgement waits for the physical write and exact storage readback', async () => {
  const f = fixture(), store = await f.openPlayableJobObservation(), write = deferred(); let saved = false;
  f.wire.set = async (key, value) => { await write.promise; f.rows.set(key, value); };
  const pending = store.set(retained).then(() => { saved = true; }); await tick();
  assert.equal(f.calls.filter(call => call.kind === 'set').length, 1); assert.equal(saved, false); assert.equal(f.rows.size, 0);
  write.resolve(); await pending; assert.equal(saved, true);
  assert.equal(f.calls.at(-1).kind, 'get'); assert.deepEqual(await store.get(), retained); store.dispose();
});

test('write failures and corrupt receipts never report successful retention or silently discard a job', async () => {
  const f = fixture(), store = await f.openPlayableJobObservation();
  f.wire.set = async () => { throw new Error('native unavailable'); }; await assert.rejects(store.set(retained));
  assert.equal(f.rows.size, 0);
  f.wire.set = async (key, value) => { f.rows.set(key, value.slice(0, -1)); };
  await assert.rejects(store.set(retained)); await assert.rejects(store.get());
  assert.equal(f.calls.filter(call => call.kind === 'remove').length, 0);
  store.dispose();
});

test('older terminal completion and older metadata updates cannot erase or replace a newer retained job', async () => {
  const f = fixture(), first = await f.openPlayableJobObservation(), second = await f.openPlayableJobObservation();
  await first.set(retained); assert.equal(await first.clear('different-job'), false);
  await assert.rejects(second.set({ jobId: 'job-newer', kind: 'repair' }));
  assert.equal(await first.clear(retained.jobId), true);
  await second.set({ jobId: 'job-newer', kind: 'repair' });
  assert.equal(await first.clear(retained.jobId), false);
  await assert.rejects(first.set({ ...retained, errorCode: 'late_original_result' }));
  assert.deepEqual(await second.get(), { jobId: 'job-newer', kind: 'repair' }); first.dispose(); second.dispose();
});

test('all handles serialize read-modify-write dismissal before a newer observation can commit', async () => {
  const f = fixture(), first = await f.openPlayableJobObservation(), second = await f.openPlayableJobObservation();
  await first.set(retained); const remove = deferred();
  f.wire.remove = async key => { await remove.promise; f.rows.delete(key); };
  const clearing = first.clear(retained.jobId); await tick();
  let newerCommitted = false;
  const replacing = second.set({ jobId: 'job-newer' }).then(() => { newerCommitted = true; }); await tick();
  assert.equal(newerCommitted, false); assert.equal(f.calls.filter(call => call.kind === 'set').length, 1);
  remove.resolve(); assert.equal(await clearing, true); await replacing;
  assert.deepEqual(await second.get(), { jobId: 'job-newer' }); assert.equal(await first.clear(retained.jobId), false);
  first.dispose(); second.dispose();
});

test('account switches cancel a stalled write immediately without crossing retained owner keys', async () => {
  const f = fixture(), old = await f.openPlayableJobObservation(), write = deferred();
  f.wire.set = async (key, value) => { if (key.includes('creator%2Bone')) await write.promise; f.rows.set(key, value); };
  const saving = old.set(retained); await tick(); f.change();
  await assert.rejects(saving, /account changed|cancel/i); assert.equal(old.current(), false);
  const current = await f.openPlayableJobObservation(); await current.set({ jobId: 'second-account-job' });
  assert.deepEqual(await current.get(), { jobId: 'second-account-job' });
  write.resolve(); await tick(); assert.deepEqual(await current.get(), { jobId: 'second-account-job' });
  assert.equal(f.rows.size, 2); old.dispose(); current.dispose(); assert.equal(f.observers.size, 0);
});

test('returning to the same account waits for old native custody then restores the original job', async () => {
  const f = fixture(), old = await f.openPlayableJobObservation(), write = deferred();
  f.wire.set = async (key, value) => { await write.promise; f.rows.set(key, value); };
  const saving = old.set(retained); await tick(); f.change(); await assert.rejects(saving);
  f.change('creator+one@example.test'); const restored = await f.openPlayableJobObservation(); let readFinished = false;
  const reading = restored.get().then(value => { readFinished = true; return value; }); await tick();
  assert.equal(readFinished, false); write.resolve(); assert.deepEqual(await reading, retained);
  old.dispose(); restored.dispose();
});

test('external cancellation and unmount detach observation without deleting the retained backend job reference', async () => {
  const f = fixture(), controller = new AbortController(), store = await f.openPlayableJobObservation(controller.signal);
  await store.set(retained); controller.abort(); assert.equal(store.current(), false);
  await assert.rejects(store.get()); await assert.rejects(store.clear(retained.jobId));
  assert.equal(f.calls.filter(call => call.kind === 'remove').length, 0); store.dispose();
  const current = await f.openPlayableJobObservation(); assert.deepEqual(await current.get(), retained);
  current.dispose(); assert.equal(f.observers.size, 0);
});

test('unverified identity and account changes while resolving scope never admit storage access', async () => {
  for (const identity of [{ tenantId: 'default', principalId: 'anonymous' }, { tenantId: '', principalId: 'owner' },
    { tenantId: 'tenant', principalId: ' owner ' }, { tenantId: 'tenant', principalId: '' }]) {
    const f = fixture(); f.wire.identity = async () => identity;
    await assert.rejects(f.openPlayableJobObservation()); assert.equal(f.calls.length, 0); assert.equal(f.observers.size, 0);
  }
  const f = fixture(), identity = deferred(); f.wire.identity = () => identity.promise;
  const opening = f.openPlayableJobObservation(); f.change(); await assert.rejects(opening, /account changed|cancel/i);
  identity.resolve({ tenantId: 'tenant', principalId: 'old@example.test' }); await tick();
  assert.equal(f.calls.length, 0); assert.equal(f.observers.size, 0);
});

test('a UI retention timeout preserves physical queue custody and cannot let an older write win later', async t => {
  const nativeTimer = global.setTimeout, deadlines = [];
  global.setTimeout = (callback, ms, ...args) => {
    if (ms === 3000) { const timer = nativeTimer(() => {}, 60000); deadlines.push(callback); return timer; }
    return nativeTimer(callback, ms, ...args);
  };
  t.after(() => { global.setTimeout = nativeTimer; });
  const f = fixture(), store = await f.openPlayableJobObservation(), firstWrite = deferred(); let writes = 0;
  f.wire.set = async (key, value) => { if (++writes === 1) await firstWrite.promise; f.rows.set(key, value); };
  const saving = store.set(retained); await tick(); deadlines[0](); await assert.rejects(saving, /not confirmed/i);
  const next = store.set({ ...retained, errorCode: 'observation_disconnected' }); await tick(); assert.equal(writes, 1);
  firstWrite.resolve(); await next; assert.equal(writes, 2);
  assert.equal((await store.get()).errorCode, 'observation_disconnected'); store.dispose();
});

test('corrupt, oversized or unsupported local receipts are retained as errors rather than silently cleared', async () => {
  const f = fixture(), store = await f.openPlayableJobObservation(); await store.set(retained);
  const key = [...f.rows.keys()][0];
  for (const raw of ['invalid json', '', 'x'.repeat(2049), JSON.stringify({ schema_version: 2, record: retained }),
    JSON.stringify({ schema_version: 1, record: { ...retained, prompt: 'private' } })]) {
    f.rows.set(key, raw); await assert.rejects(store.get()); await assert.rejects(store.clear(retained.jobId));
    assert.equal(f.rows.get(key), raw);
  }
  assert.equal(f.calls.filter(call => call.kind === 'remove').length, 0); store.dispose();
});

test('backend unconfirmed status retains only bounded request identity and never classifies terminal', () => {
  const f = fixture(); const data = { job_status: 'unconfirmed', error_code: retained.errorCode, engine_request_key: retained.engineRequestKey, retry_same_request: true };
  assert.deepEqual(f.playableJobUnconfirmed(data), { errorCode: retained.errorCode, engineRequestKey: retained.engineRequestKey });
  assert.deepEqual(f.playableJobUnconfirmed({ ok: true, data }), { errorCode: retained.errorCode, engineRequestKey: retained.engineRequestKey });
  assert.equal(lifecycle.classifyBuildJob({ data }), 'pending');
  for (const value of [null, [], { ok: false, data }, { job_status: 'done' }, { job_status: 'error' }, { retry_same_request: true }, { data: 'invalid', job_status: 'unconfirmed' }]) assert.equal(f.playableJobUnconfirmed(value), null);
  assert.deepEqual(f.playableJobUnconfirmed({ job_status: 'unconfirmed', error_code: 'private prompt text', engine_request_key: 'x'.repeat(257) }), {});
});

function playableClosure(name, bindings) {
  const source = fs.readFileSync(path.join(ROOT, 'app/playable.tsx'), 'utf8');
  const syntax = ts.createSourceFile('playable.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let callback;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(syntax) === name && ts.isCallExpression(node.initializer)) callback = node.initializer.arguments[0].getText(syntax);
    ts.forEachChild(node, visit);
  }
  visit(syntax); assert.ok(callback, 'real playable closure ' + name);
  const output = ts.transpileModule('module.exports = (' + callback + ');', { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } });
  const module = { exports: {} }, names = Object.keys(bindings);
  compileFunction(output.outputText, ['module', ...names])(module, ...names.map(key => bindings[key]));
  return module.exports;
}
function observationClosureFixture() {
  const newer = { jobId: 'job-newer-observation', kind: 'repair' };
  let stored = { ...retained };
  const state = { saved: stored, message: '', busy: true, observing: true }, calls = [];
  const observationRequest = { current: null }, pageActive = { current: true };
  const store = { current: () => true, get: async () => ({ ...stored }), set: async value => { stored = { ...value }; },
    clear: async id => { calls.push({ kind: 'clear', id }); stored = { ...newer }; return false; } };
  const bindings = {
    observationRequest, observationStore: { current: store }, pageActive, savedJob: retained,
    getAuthEpoch: () => 0, watchBuildJob: lifecycle.watchBuildJob, classifyBuildJob: lifecycle.classifyBuildJob,
    playableJobUnconfirmed: fixture().playableJobUnconfirmed,
    api: { get: async (url, options) => { calls.push({ kind: 'get', url, options }); return { ok: true, data: { job_id: retained.jobId, job_status: 'error', error: 'confirmed failure' } }; },
      post: async () => { throw new Error('Observation cannot submit or replay work'); } },
    setSavedJob: value => { state.saved = value; }, setObservationMessage: value => { state.message = value; },
    setObservingJob: value => { state.observing = value; }, setBusy: value => { state.busy = value; }, setBusyLabel() {},
  };
  return { newer, state, calls, observationRequest, bindings, stored: () => stored };
}

test('actual terminal observation closure retains a newer reference when compare-and-clear returns false', async () => {
  const f = observationClosureFixture(); await playableClosure('pollJob', f.bindings)(retained.jobId);
  assert.deepEqual(f.stored(), f.newer); assert.deepEqual(f.state.saved, f.newer);
  assert.match(f.state.message, /different job reference/i); assert.equal(f.state.busy, false); assert.equal(f.state.observing, false);
  assert.equal(f.calls.filter(call => call.kind === 'get').length, 1);
  assert.equal(f.calls.find(call => call.kind === 'get').url, '/api/playable/job/' + retained.jobId);
  assert.deepEqual(f.calls.filter(call => call.kind === 'clear'), [{ kind: 'clear', id: retained.jobId }]);
  assert.equal(f.observationRequest.current, null);
});

test('actual dismiss closure stops only its observation and keeps a different retained job visible', async () => {
  const f = observationClosureFixture(), monitoring = new AbortController(); f.observationRequest.current = monitoring;
  await playableClosure('dismissJobObservation', f.bindings)();
  assert.equal(monitoring.signal.aborted, true); assert.equal(f.observationRequest.current, null);
  assert.deepEqual(f.stored(), f.newer); assert.deepEqual(f.state.saved, f.newer);
  assert.match(f.state.message, /not been dismissed/i); assert.equal(f.state.busy, false); assert.equal(f.state.observing, false);
  assert.equal(f.calls.some(call => call.kind === 'get'), false);
});
