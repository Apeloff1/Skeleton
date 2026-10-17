'use strict';
const { compileFunction } = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function loadTS(file, mocks = {}) {
  const result = ts.transpileModule(fs.readFileSync(path.join(ROOT, file), 'utf8'), {
    fileName: file, compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    }, reportDiagnostics: true,
  });
  assert.equal(result.diagnostics.length, 0, file);
  const module = { exports: {} };
  compileFunction(result.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(mocks, id), file + ' unexpected module ' + id);
    return mocks[id];
  }, module, module.exports);
  return module.exports;
}
const reducer = loadTS('services/operationStreamReducer.ts');
const { OperationBrowserSession } = loadTS('services/operationStreamSession.ts', {
  './operationStreamReducer.ts': reducer,
});
function operation(state = 'running') {
  return {
    operation_id: 'work-1', tenant_id: 't', actor_id: 'user',
    capability: 'build', state, version: 1, identity_digest: 'abc',
    trace_id: 'trace', idempotency_key: 'key', created_at: '', deadline: '', updated_at: '',
  };
}
function replay(after = 0, count = 0, terminal = false) {
  const events = Array.from({ length: count }, (_, i) => ({
    schema_version: 1, operation_id: 'work-1', event_id: 'event-' + (after + i + 1),
    sequence: after + i + 1, type: 'operation.progress', timestamp: '2026-10-17T00:00:00Z',
    payload: {},
  }));
  return { ok: true, payload: {
    ok: true, operation: operation(terminal ? 'completed' : 'running'),
    events, after_sequence: after, latest_sequence: after + count,
    stream_latest_sequence: after + count, has_more: false, terminal,
    canonical_result: terminal ? { status: 'completed', final_output: 'done' } : undefined,
  } };
}
function store() {
  let sequence = 0;
  return {
    get sequence() { return sequence; },
    load: async () => sequence,
    save: async (_operation, _consumer, value) => { sequence = value; },
    clear: async () => { sequence = 0; },
  };
}
function transport() {
  return {
    replay: async (_id, _consumer, after) => replay(after),
    acknowledge: async () => ({ ok: true }),
    resync: async () => null,
    cancel: async () => ({ ok: true }),
  };
}
function session(t = transport(), st = store(), opts = {}) {
  return new OperationBrowserSession('work-1', t, st, {
    consumerId: 'test-consumer', ...opts,
  });
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('transport replay rejection yields explicit error state instead of escaping follow', async () => {
  const t = transport();
  t.replay = async () => { throw new Error('network lost'); };
  const app = session(t);
  const state = await app.follow();
  assert.equal(state.connection, 'error');
  assert.equal(state.error, 'replay_transport_unavailable');
  assert.equal(state.terminal, false);
});

test('transport acknowledgement rejection preserves cursor and reports recoverable error', async () => {
  const st = store();
  const t = transport();
  t.replay = async (_id, _consumer, after) => replay(after, 1);
  t.acknowledge = async () => { throw new Error('ack unavailable'); };
  const current = await session(t, st).replayOnce();
  assert.equal(current.connection, 'error');
  assert.equal(current.error, 'cursor_ack_unavailable');
  assert.equal(st.sequence, 1);
});

test('optional observer exceptions do not affect authoritative stream state', async () => {
  const app = session(transport(), store(), {
    onState: () => { throw new Error('UI callback threw'); },
  });
  const state = await app.replayOnce();
  assert.equal(state.connection, 'following');
  assert.equal(app.state.lastSequence, 0);
});

test('authoritative resync transport failure remains an explicit error state', async () => {
  const t = transport();
  t.resync = async () => { throw new Error('server down'); };
  const app = session(t);
  const state = await app.resync();
  assert.equal(state.connection, 'error');
  assert.equal(state.error, 'authoritative_resync_unavailable');
});

test('cancellation transport error does not report successful backend cancellation', async () => {
  const t = transport();
  t.cancel = async () => { throw new Error('unavailable'); };
  const result = await session(t).cancel();
  assert.deepEqual(result, { ok: false, error: 'cancel_transport_unavailable' });
});

test('concurrent replay calls share one network request', async () => {
  const t = transport();
  let calls = 0, release;
  t.replay = () => new Promise(resolve => { calls++; release = resolve; });
  const app = session(t);
  const a = app.replayOnce();
  const b = app.replayOnce();
  assert.equal(a, b);
  await settle();
  assert.equal(calls, 1);
  release(replay());
  await Promise.all([a,b]);
});

test('clearing a cursor invalidates a delayed old replay response', async () => {
  const t = transport();
  let release;
  t.replay = () => new Promise(resolve => { release = resolve; });
  const st = store();
  const app = session(t, st, {
    initialState: reducer.createOperationClientState('work-1'),
  });
  const original = app.replayOnce();
  await settle();
  await app.clearCursor();
  release(replay(0, 1));
  const state = await original;
  assert.equal(state.lastSequence, 0);
  assert.equal(app.state.lastSequence, 0);
  assert.equal(st.sequence, 0);
});

test('cursor clearing physically follows a started native save, never vice versa', async () => {
  const st = store();
  const calls = [];
  let releaseWrite;
  st.save = () => new Promise(resolve => {
    calls.push('save-start');
    releaseWrite = () => { calls.push('save-done'); resolve(); };
  });
  st.clear = async () => { calls.push('clear'); };
  const t = transport();
  t.replay = async (_id, _consumer, after) => replay(after, 1);
  const app = session(t, st, {
    initialState: reducer.createOperationClientState('work-1'),
  });
  const old = app.replayOnce();
  await settle();
  assert.deepEqual(calls, ['save-start']);
  const clearing = app.clearCursor();
  await settle();
  assert.deepEqual(calls, ['save-start']);
  releaseWrite();
  await Promise.all([old, clearing]);
  assert.deepEqual(calls, ['save-start','save-done','clear']);
  assert.equal(app.state.lastSequence, 0);
});

test('idle follow polls exponentially back off but still observes completion', async () => {
  const t = transport();
  let fetches = 0;
  t.replay = async (_id, _consumer, after) => {
    fetches++;
    return replay(after, 0, fetches >= 4);
  };
  const originalSet = global.setTimeout;
  const originalClear = global.clearTimeout;
  const delays = [];
  global.setTimeout = (fn, delay) => {
    delays.push(delay);
    queueMicrotask(fn);
    return { id: delays.length };
  };
  global.clearTimeout = () => {};
  try {
    const app = session(t, store(), { pollMs: 100, maxPollMs: 350 });
    const state = await app.follow();
    assert.equal(state.connection, 'terminal');
    assert.equal(state.displayedAssistantContent, 'done');
    assert.deepEqual(delays, [100, 200, 350]);
  } finally {
    global.setTimeout = originalSet;
    global.clearTimeout = originalClear;
  }
});

test('replay history keeps bounded reducer data under hundreds of event batches', async () => {
  const st = store();
  const t = transport();
  t.replay = async (_id, _consumer, after) => replay(after, 10);
  const app = session(t, st);
  for (let i=0; i<30; i++) {
    const result = await app.replayOnce();
    assert.equal(result.resyncRequired, false);
  }
  assert.ok(app.state.events.length <= reducer.MAX_RETAINED_OPERATION_EVENTS);
  assert.ok(app.state.seenEventIds.length <= reducer.MAX_RETAINED_EVENT_IDS);
  assert.equal(app.state.lastSequence, 300);
});
