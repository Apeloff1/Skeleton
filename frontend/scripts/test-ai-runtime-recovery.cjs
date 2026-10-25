'use strict';
/* Execute the real controller and transport against isolated owner fixtures.
 * No Expo runtime, provider, external network or generated transcript is used. */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function load(relative, imports = {}) {
  const source = fs.readFileSync(path.join(ROOT, relative), 'utf8');
  const output = ts.transpileModule(source, { fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } });
  assert.equal(output.diagnostics.length, 0, relative + ' must compile');
  const module = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), 'Unexpected integration: ' + relative + ': ' + id);
    return imports[id];
  }, module, module.exports);
  return module.exports;
}
const errors = load('src/product/chatErrors.ts');
const cooperation = load('src/product/chatCooperation.ts', { './chatErrors': errors });
const policy = load('src/utils/requestRecoveryPolicy.ts');
const turnKey = 'chat:original-1';
const threadId = '11111111-1111-4111-8111-111111111111';
const otherId = '22222222-2222-4222-8222-222222222222';
function thread(id = threadId) { return { thread_id: id, title: 'Saved conversation', state: 'active', version: 1,
  message_sequence: 0, updated_at: '2026-10-22T12:00:00.000Z' }; }
const model = id => ({ id, provider_id: 'local', model_id: id, available: true, selectable: true, active: id === 'model-1',
  max_output_tokens: 4096, default_output_tokens: 1024, capabilities: ['text-generation'] });
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function controllerFixture({ saved = null, messages = [] } = {}) {
  let token = 'account-token-1';
  const disk = new Map();
  const storageKey = 'canonical-chat-ui:v1:tenant-1:actor-1';
  if (saved) disk.set(storageKey, JSON.stringify({ schema_version: 1, activeThreadId: threadId,
    selectedModelId: 'model-1', pendingTurns: [{ threadId, idempotencyKey: turnKey, lastEventId: 0, ...saved }] }));
  const calls = { submit: [], resume: 0, cancel: 0, lookups: [], opens: [] };
  const wire = {
    identity: async () => ({ tenantId: 'tenant-1', principalId: 'actor-1' }),
    turn: async (id, key) => ({ success: false, accepted: false, terminal: false, state: 'prepared', thread: thread(id),
      user_message: { message_id: 'user-1', thread_id: id, sequence: 1, author_type: 'user', idempotency_key: key, content: 'Saved question', attachment_refs: [] } }),
    open: async id => ({ thread: thread(id), messages: id === threadId ? messages : [] }),
    submit: async () => { throw new errors.ChatClientError('Admission was not confirmed.', { kind: 'unavailable', status: 503 }); },
    cancel: async () => { throw new errors.ChatClientError('Turn not found.', { status: 404 }); },
  };
  const conversation = {
    listConversationPage: async () => ({ threads: [thread(), thread(otherId)], nextCursor: null }),
    reconstructConversation: async id => { calls.opens.push(id); return wire.open(id); },
    getConversationRecovery: async id => ({ thread: thread(id), messages: [], pending_turn: null, regeneration_requests: [] }),
    getConversationTurn: async (id, key) => { calls.lookups.push({ id, key }); return wire.turn(id, key); },
    cancelConversationTurn: async (...args) => { calls.cancel++; return wire.cancel(...args); },
    resumeConversationTurn: async (id, key) => { calls.resume++; return wire.turn(id, key); },
    createConversation: async () => thread('33333333-3333-4333-8333-333333333333'),
  };
  const ai = {
    getChatModels: async () => ({ models: [model('model-1'), model('model-2')] }),
    validateChatTurn: (value, expectedThread, expectedKey) => {
      if (value.thread) assert.equal(value.thread.thread_id, expectedThread);
      if (value.user_message) assert.equal(value.user_message.idempotency_key, expectedKey);
      return value;
    },
    submitChatTurn: async (owner, request) => { calls.submit.push({ owner, request }); return wire.submit(owner, request); },
    followChatTurn: (_id, _key, options) => new Promise((_, reject) => {
      const abort = () => reject(new errors.ChatClientError('Detached.', { kind: 'cancelled' }));
      if (options.signal.aborted) abort(); else options.signal.addEventListener('abort', abort, { once: true });
    }),
  };
  const { ChatController } = load('src/product/chatController.ts', {
    '@react-native-async-storage/async-storage': { getItem: async key => disk.get(key) ?? null,
      setItem: async (key, value) => { disk.set(key, value); } },
    '../auth/gameforgeAuth': { getAuthToken: () => token, resolveStorageTenantIdentity: () => wire.identity() },
    './governedConversationClient': conversation, './aiChatClient': ai,
    './chatErrors': errors, './chatCooperation': cooperation,
  });
  const controller = new ChatController();
  return { controller, calls, wire, disk, storageKey, setToken(value) { token = value; } };
}

test('read-only reconnect never admits a prepared turn and retains the exact key', async t => {
  const f = controllerFixture({ saved: {} }); t.after(() => f.controller.dispose());
  await f.controller.initialize();
  await f.controller.reconnect();
  assert.equal(f.calls.resume, 0); assert.equal(f.calls.submit.length, 0);
  assert.equal(f.controller.getSnapshot().pending.idempotencyKey, turnKey);
  assert.equal(f.controller.getSnapshot().pending.accepted, false);
  assert.equal(f.controller.getSnapshot().error.code, 'awaiting_admission');
  assert.ok(f.calls.lookups.every(call => call.key === turnKey));
});

test('503 and ownership-conflict reconciliation retain pending identity without replay', async t => {
  const f = controllerFixture({ saved: {} }); t.after(() => f.controller.dispose());
  await f.controller.initialize();
  for (const status of [503, 409, 502]) {
    f.wire.turn = async () => { throw new errors.ChatClientError('Unconfirmed owner.', { status, kind: status === 409 ? 'conflict' : 'unavailable' }); };
    await assert.rejects(f.controller.reconnect(), error => error.status === status);
    assert.equal(f.controller.getSnapshot().pending.idempotencyKey, turnKey);
    assert.equal(f.calls.submit.length, 0); assert.equal(f.calls.resume, 0);
  }
});

test('missing saved turn stays unresolved and cannot silently create another request', async t => {
  const f = controllerFixture({ saved: {} }); t.after(() => f.controller.dispose());
  f.wire.turn = async () => { throw new errors.ChatClientError('Not found.', { status: 404 }); };
  await f.controller.initialize();
  assert.equal(f.controller.getSnapshot().pending.idempotencyKey, turnKey);
  await assert.rejects(f.controller.send('Replacement question'), error => error.kind === 'conflict');
  await assert.rejects(f.controller.retry(), error => error.code === 'original_request_required');
  assert.equal(f.calls.submit.length, 0);
  await f.controller.newConversation();
  assert.equal(f.controller.getSnapshot().activeThread.thread_id, '33333333-3333-4333-8333-333333333333');
  f.controller.dispose(); await tick();
  const saved = JSON.parse(f.disk.get(f.storageKey));
  assert.equal(saved.pendingTurns.find(row => row.threadId === threadId).idempotencyKey, turnKey);
});

test('a saved Stop survives remount and Resume never re-admits it', async t => {
  const f = controllerFixture({ saved: { stopRequested: true } }); t.after(() => f.controller.dispose());
  await f.controller.initialize();
  assert.equal(f.controller.getSnapshot().pending.stopRequested, true);
  await assert.rejects(f.controller.retry(), error => error.status === 404);
  assert.equal(f.calls.cancel, 1); assert.equal(f.calls.resume, 0); assert.equal(f.calls.submit.length, 0);
  f.controller.dispose(); await tick();
  assert.equal(JSON.parse(f.disk.get(f.storageKey)).pendingTurns[0].stopRequested, true);
});

test('thread switches retain the original model, budget, context and key after ambiguous admission', async t => {
  const f = controllerFixture(); t.after(() => f.controller.dispose());
  await f.controller.initialize();
  await assert.rejects(f.controller.send('Original question', { maxOutputTokens: 768, context: 'Original project context' }));
  const original = f.calls.submit[0];
  f.controller.selectModel('model-2');
  await f.controller.openConversation(otherId);
  f.wire.turn = async () => { throw new errors.ChatClientError('Not found.', { status: 404 }); };
  await assert.rejects(f.controller.openConversation(threadId));
  f.wire.submit = async () => ({ success: false, accepted: true, terminal: false, state: 'running', operation_id: 'operation-1' });
  await f.controller.retry();
  assert.equal(f.calls.submit.length, 2);
  const replay = f.calls.submit[1];
  assert.equal(replay.request.idempotencyKey, original.request.idempotencyKey);
  assert.equal(replay.request.message, 'Original question');
  assert.equal(replay.request.model.id, 'model-1');
  assert.equal(replay.request.maxOutputTokens, 768);
  assert.equal(replay.request.context, 'Original project context');
});

test('Stop queued during ambiguous submission remains a Stop after the response fails', async t => {
  const f = controllerFixture(); t.after(() => f.controller.dispose());
  await f.controller.initialize();
  const pending = deferred(); f.wire.submit = () => pending.promise;
  const sending = f.controller.send('Original question');
  await tick();
  await f.controller.cancel();
  pending.reject(new errors.ChatClientError('Unconfirmed.', { status: 503, kind: 'unavailable' }));
  await assert.rejects(sending); await tick();
  assert.equal(f.calls.submit.length, 1); assert.equal(f.calls.cancel, 1);
  assert.equal(f.controller.getSnapshot().pending.stopRequested, true);
  await assert.rejects(f.controller.retry());
  assert.equal(f.calls.submit.length, 1); assert.equal(f.calls.resume, 0); assert.equal(f.calls.cancel, 2);
});

test('retry reopens the failed selected thread instead of reporting an empty successful load', async t => {
  const f = controllerFixture(); t.after(() => f.controller.dispose());
  let opens = 0;
  f.wire.open = async id => { if (++opens === 1) throw new errors.ChatClientError('Storage temporarily unavailable.', { kind: 'unavailable' }); return { thread: thread(id), messages: [] }; };
  await f.controller.initialize();
  assert.equal(f.controller.getSnapshot().activeThread, null);
  await f.controller.reconnect();
  assert.deepEqual(f.calls.opens, [threadId, threadId]);
  assert.equal(f.controller.getSnapshot().activeThread.thread_id, threadId);
});

test('a completion record without a canonical answer cannot release the saved turn', async t => {
  const f = controllerFixture({ saved: {} }); t.after(() => f.controller.dispose());
  await f.controller.initialize();
  f.wire.turn = async () => ({ success: true, terminal: true, state: 'completed', thread: thread() });
  await assert.rejects(f.controller.reconnect(), error => error.code === 'canonical_reply_missing');
  assert.equal(f.controller.getSnapshot().pending.idempotencyKey, turnKey);
});

test('account change during identity resolution prevents the next turn lookup', async t => {
  const f = controllerFixture({ saved: {} }); t.after(() => f.controller.dispose());
  await f.controller.initialize(); const before = f.calls.lookups.length;
  const identity = deferred(); f.wire.identity = () => identity.promise;
  const reading = f.controller.reconnect();
  f.setToken('different-account'); identity.resolve({ tenantId: 'tenant-1', principalId: 'actor-1' });
  await assert.rejects(reading, error => error.kind === 'authorization');
  assert.equal(f.calls.lookups.length, before);
  assert.equal(f.controller.getSnapshot().accountScope, null);
  assert.deepEqual(f.controller.getSnapshot().messages, []);
});

function transportFixture() {
  return load('src/utils/apiClient.ts', {
    './apiBase': { API_BASE: 'https://backend.test' },
    './requestRecoveryPolicy': policy,
    './breadcrumbs': { trail: { add() {} } },
    './bootTracer': { traceStep: async () => {} },
  });
}
function restoreGlobal(t, name, value) {
  const original = global[name]; global[name] = value;
  t.after(() => { if (original === undefined) delete global[name]; else global[name] = original; });
}
test('the real transport does not replay writes for an invented idempotency header', async t => {
  let calls = 0;
  restoreGlobal(t, 'fetch', async () => { calls++; return new Response('{"detail":"unavailable"}', { status: 503 }); });
  const { safeFetch } = transportFixture();
  const result = await safeFetch('/api/galaxy-studio/expand', { method: 'POST', body: { build_id: 'build-1' }, retries: 9,
    headers: { 'Idempotency-Key': 'invented-client-key' } });
  assert.equal(result.ok, false); assert.equal(result.status, 503); assert.equal(calls, 1);
});

test('caller cancellation settles even when a native adapter ignores abort during its body read', async t => {
  const body = deferred(), readingBody = deferred();
  restoreGlobal(t, 'fetch', async () => ({ ok: true, status: 200, headers: new Headers(),
    text: () => { readingBody.resolve(); return body.promise; } }));
  const { safeFetch } = transportFixture(); const cancel = new AbortController();
  const request = safeFetch('/api/status', { signal: cancel.signal, retries: 0 });
  await readingBody.promise; cancel.abort();
  const result = await request;
  assert.equal(result.ok, false); assert.equal(result.error, 'aborted');
  body.resolve('{"late":"must not win"}');
});

test('the response-body deadline covers a stalled native text adapter', async t => {
  const body = deferred(); let bodyReads = 0;
  restoreGlobal(t, 'fetch', async () => ({ ok: true, status: 200, headers: new Headers(), text: () => { bodyReads++; return body.promise; } }));
  const { safeFetch } = transportFixture();
  const result = await safeFetch('/api/status', { timeoutMs: 250, retries: 0 });
  assert.equal(result.ok, false); assert.equal(result.error, 'timeout'); assert.equal(bodyReads, 1);
  body.resolve('{"late":true}');
});

test('oversized streamed responses cancel before assembling an unbounded document', async () => {
  const { readBoundedResponseText } = transportFixture(); let cancelled = false, chunks = 0;
  const response = new Response(new ReadableStream({ pull(controller) { chunks++; controller.enqueue(new Uint8Array(800)); }, cancel() { cancelled = true; } }));
  const result = await readBoundedResponseText(response, 1024);
  assert.equal(result.oversized, true); assert.equal(result.text, '');
  assert.equal(cancelled, true); assert.ok(chunks <= 3);
});

test('stream decoding preserves UTF-8 split inside every multibyte character', async () => {
  const { readBoundedResponseText } = transportFixture();
  const original = JSON.stringify({ answer: 'Jeeves 🐉 café 日本語' });
  const bytes = new TextEncoder().encode(original); let offset = 0;
  const response = new Response(new ReadableStream({ pull(controller) { if (offset === bytes.length) controller.close(); else controller.enqueue(bytes.slice(offset, ++offset)); } }));
  const result = await readBoundedResponseText(response, 1024);
  assert.equal(result.oversized, false); assert.deepEqual(JSON.parse(result.text), JSON.parse(original));
});

test('account-bearing and query-bearing GETs cannot reuse a public session cache', async t => {
  const memory = new Map(); let requests = 0;
  restoreGlobal(t, 'sessionStorage', { getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value) });
  restoreGlobal(t, 'fetch', async () => new Response(JSON.stringify({ number: ++requests }), { status: 200 }));
  const api = transportFixture().default;
  await api.get('/api/public', { cacheKey: 'same-key', retries: 0 });
  await api.get('/api/public', { cacheKey: 'same-key', retries: 0 });
  assert.equal(requests, 1);
  await api.get('/api/private', { cacheKey: 'same-key', headers: { Authorization: 'Bearer actor-1' }, retries: 0 });
  await api.get('/api/private', { cacheKey: 'same-key', headers: { Authorization: 'Bearer actor-2' }, retries: 0 });
  await api.get('/api/private?token=actor-1', { cacheKey: 'same-key', retries: 0 });
  await api.get('/api/private?token=actor-2', { cacheKey: 'same-key', retries: 0 });
  assert.equal(requests, 5); assert.equal(memory.size, 1);
  const abort = new AbortController(); abort.abort();
  const cancelled = await api.get('/api/public', { cacheKey: 'same-key', signal: abort.signal });
  assert.equal(cancelled.error, 'aborted'); assert.equal(requests, 5);
});
