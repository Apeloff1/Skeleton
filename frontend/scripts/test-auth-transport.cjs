'use strict';
// Execute the actual HTTP/auth owners with only platform and I/O seams stubbed.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function load(relative, imports) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, relative), 'utf8'), {
    fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  assert.equal(output.diagnostics.length, 0);
  const module = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])(id => {
    // Native SSE is unavailable in this browser-style transport fixture.
    if (id === 'expo/fetch') throw new Error('not_native');
    assert.ok(Object.hasOwn(imports, id), relative + ': unexpected dependency ' + id);
    return imports[id];
  }, module, module.exports);
  return module.exports;
}
const policy = load('src/utils/requestRecoveryPolicy.ts', {});
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function replace(t, name, value) {
  const previous = global[name]; global[name] = value;
  t.after(() => { if (previous === undefined) delete global[name]; else global[name] = previous; });
}
function fixture(token = '', backend = 'https://backend.test') {
  let epoch = 0, cacheClears = 0;
  const observers = new Set();
  const owner = {
    getAuthToken: () => token, getAuthEpoch: () => epoch,
    initializeStoredToken: async () => {},
    subscribeAuthChanges: observer => { observers.add(observer); return () => observers.delete(observer); },
  };
  const transport = load('src/utils/apiClient.ts', {
    './apiBase': { API_BASE: backend }, './requestRecoveryPolicy': policy,
    './breadcrumbs': { trail: { add() {} } }, './bootTracer': { traceStep: async () => {} },
    '../foundation/queryCache': { appQueryCache: { clear() { cacheClears++; } } },
    '../auth/gameforgeAuth': owner,
  });
  return { ...transport, owner, change(value) { token = value; epoch++; for (const observer of observers) observer(); },
    cacheClears: () => cacheClears };
}
function storage() {
  const rows = new Map(); return { rows, get length() { return rows.size; }, key: i => [...rows.keys()][i] ?? null,
    getItem: key => rows.get(key) ?? null, setItem: (key, value) => rows.set(key, value), removeItem: key => rows.delete(key) };
}

test('API, envelope and SSE clients hydrate the canonical token before the first protected read', async t => {
  const calls = [], f = fixture();
  f.owner.initializeStoredToken = async () => { f.owner.getAuthToken = () => 'stored-account'; };
  replace(t, 'fetch', async (url, init) => { calls.push({ url, init }); return new Response('', { headers: { 'content-type': 'text/event-stream' } }); });
  await f.default.get('/api/playable/projects', { retries: 0 });
  await f.safeFetch('/api/memory/notes', { retries: 0 });
  assert.deepEqual(await f.openEventStream('/api/playable/events', { onChunk() {} }), { kind: 'eof' });
  assert.equal(calls.length, 3);
  for (const call of calls) { assert.equal(call.init.headers.Authorization, 'Bearer stored-account'); assert.equal(call.init.redirect, 'error'); }
});

test('automatic product JWT stays inside the configured backend API and conversations exception', async t => {
  const calls = [], f = fixture('account-1');
  replace(t, 'fetch', async (url, init) => { calls.push({ url, init }); return new Response('{}'); });
  const excluded = [
    'https://external.test/api/private', 'https://backend.test.evil.test/api/private',
    'https://backend.test:444/api/private', 'http://backend.test/api/private',
    'https://user@backend.test/api/private', 'https://backend.test/public',
    '/api/v1/ai/execute', '/api/v1', '/api//v1/ai/execute', '/api/%76%31/ai/execute',
    '/api/v1/conversations-foreign', '/api/v1/conversations%2f..%2fai/execute',
  ];
  for (const url of excluded) await f.safeFetch(url, { retries: 0 });
  for (const { init } of calls) assert.equal(init.headers.Authorization, undefined);
  for (const url of ['/api/private', '/api/v1/conversations', '/api/v1/conversations/thread-1/messages']) {
    await f.safeFetch(url, { retries: 0 }); assert.equal(calls.at(-1).init.headers.Authorization, 'Bearer account-1');
  }
});

test('backend base path is respected and caller-provided authorization remains exact', async t => {
  const calls = [], f = fixture('account-1', 'https://backend.test/product');
  replace(t, 'fetch', async (url, init) => { calls.push({ url, init }); return new Response('{}'); });
  await f.default.get('/api/private', { retries: 0 });
  assert.equal(calls.at(-1).url, 'https://backend.test/product/api/private');
  assert.equal(calls.at(-1).init.headers.Authorization, 'Bearer account-1');
  await f.safeFetch('https://backend.test/api/private', { retries: 0 });
  assert.equal(calls.at(-1).init.headers.Authorization, undefined);
  await f.safeFetch('/api/private', { retries: 0, headers: { authorization: 'Custom delegated-value' } });
  assert.equal(calls.at(-1).init.headers.authorization, 'Custom delegated-value');
  assert.equal(calls.at(-1).init.headers.Authorization, undefined);
});

test('anonymous requests carry no invented authorization header', async t => {
  const f = fixture(); let observed;
  replace(t, 'fetch', async (_url, init) => { observed = init; return new Response('{}'); });
  await f.default.get('/api/private', { retries: 0 });
  assert.equal(observed.headers.Authorization, undefined);
});

test('login and logout invalidate legacy/session caches and query projections', async t => {
  const memory = storage(), f = fixture(); let requests = 0;
  memory.setItem('api:legacy-user', '{"data":"private"}'); memory.setItem('unrelated-preference', 'keep');
  replace(t, 'sessionStorage', memory);
  replace(t, 'fetch', async () => new Response(JSON.stringify({ number: ++requests })));
  await f.default.get('/api/public', { cacheKey: 'shared', retries: 0 });
  await f.default.get('/api/public', { cacheKey: 'shared', retries: 0 });
  assert.equal(requests, 1); assert.equal(memory.getItem('api:legacy-user'), null);
  const before = f.cacheClears(); f.change('new-account');
  assert.equal(f.cacheClears(), before + 1); assert.equal(memory.getItem('unrelated-preference'), 'keep');
  assert.equal([...memory.rows.keys()].filter(key => key.startsWith('api:')).length, 0);
  await f.default.get('/api/public', { cacheKey: 'shared', retries: 0 });
  await f.default.get('/api/public', { cacheKey: 'shared', retries: 0 });
  assert.equal(requests, 3, 'authenticated reads cannot reuse the anonymous cache');
  f.change(''); await f.default.get('/api/public', { cacheKey: 'shared', retries: 0 });
  assert.equal(requests, 4);
});

for (const kind of ['api', 'safeFetch']) {
  test(kind + ' account change settles a stalled native body and rejects late private data', async t => {
    const f = fixture('account-1'), body = deferred(), reading = deferred(); let requestSignal;
    replace(t, 'fetch', async (_url, init) => { requestSignal = init.signal; return { ok: true, status: 200, headers: new Headers(),
      text() { reading.resolve(); return body.promise; } }; });
    const pending = kind === 'api' ? f.default.get('/api/private', { retries: 0 }) : f.safeFetch('/api/private', { retries: 0 });
    await reading.promise; f.change('account-2');
    const result = await pending;
    assert.equal(result.ok, false); assert.equal(result.error, 'aborted'); assert.equal(requestSignal.aborted, true);
    body.resolve('{"private":"old-account"}'); await tick();
    assert.equal(result.data ?? null, null);
  });
}

test('session transition clears an open circuit so a new account can make its first request', async t => {
  const f = fixture('account-1'); let requests = 0;
  replace(t, 'fetch', async () => { requests++; return new Response('{}', { status: requests <= 5 ? 503 : 200 }); });
  for (let i = 0; i < 5; i++) await f.default.get('/api/private', { retries: 0 });
  assert.equal((await f.default.get('/api/private', { retries: 0 })).error, 'circuit_open');
  assert.equal(requests, 5);
  f.change('account-2');
  assert.equal((await f.default.get('/api/private', { retries: 0 })).ok, true);
  assert.equal(requests, 6);
});

test('SSE session changes cancel a stalled reader immediately and fence late chunks', async t => {
  const f = fixture('account-1'), chunk = deferred(), reading = deferred(); let cancelled = 0, init;
  const chunks = [];
  replace(t, 'fetch', async (_url, options) => { init = options; return { ok: true, status: 200, headers: new Headers({ 'content-type': 'text/event-stream' }),
    body: { getReader: () => ({ read() { reading.resolve(); return chunk.promise; }, cancel: async () => { cancelled++; } }) } }; });
  const pending = f.openEventStream('/api/private/events', { onChunk: text => chunks.push(text) });
  await reading.promise; f.change('account-2');
  assert.deepEqual(await pending, { kind: 'aborted' }); assert.equal(init.signal.aborted, true); assert.ok(cancelled >= 1);
  chunk.resolve({ done: false, value: new TextEncoder().encode('data: old-account\n\n') }); await tick();
  assert.deepEqual(chunks, []);
});

test('SSE native text fallback rejects a late account response', async t => {
  const f = fixture('account-1'), body = deferred(), reading = deferred(), chunks = [];
  replace(t, 'fetch', async () => ({ ok: true, status: 200, text() { reading.resolve(); return body.promise; } }));
  const pending = f.openEventStream('/api/private/events', { onChunk: text => chunks.push(text) });
  await reading.promise; f.change(''); assert.deepEqual(await pending, { kind: 'aborted' });
  body.resolve('data: private\n\n'); await tick(); assert.deepEqual(chunks, []);
});

test('abort during credential hydration admits no network request', async t => {
  const f = fixture('account-1'), initialized = deferred(), started = deferred(); let requests = 0;
  f.owner.initializeStoredToken = () => { started.resolve(); return initialized.promise; };
  replace(t, 'fetch', async () => { requests++; return new Response('{}'); });
  const pending = f.safeFetch('/api/private', { retries: 0 }); await started.promise;
  f.change(''); assert.equal((await pending).error, 'aborted');
  initialized.resolve(); await tick(); assert.equal(requests, 0);
});

test('a synchronous account switch fences calls before lazy session preparation resumes', async t => {
  const f = fixture('account-1'); let requests = 0;
  replace(t, 'fetch', async () => { requests++; return new Response('{}'); });
  await f.default.get('/api/private', { retries: 0 });
  const pending = f.default.get('/api/private', { retries: 0, headers: { Authorization: 'Bearer account-1' } });
  f.change('account-2');
  assert.equal((await pending).error, 'aborted'); assert.equal(requests, 1);
});

test('logout revokes the canonical local session before waiting for server acknowledgement', async () => {
  const server = deferred(); let logoutCalls = 0, logoutHeaders;
  const auth = load('src/auth/gameforgeAuth.ts', {
    'react-native': { Platform: { OS: 'native' } },
    'expo-secure-store': { setItemAsync: async () => {}, deleteItemAsync: async () => {}, getItemAsync: async () => '' },
    'expo-web-browser': {}, 'expo-linking': {},
    '../utils/apiClient': { __esModule: true, default: { post: async (url, _body, options) => {
      if (url.endsWith('/login')) return { ok: true, data: { access_token: 'canonical-account' } };
      logoutCalls++; logoutHeaders = options.headers; return server.promise;
    } } },
  });
  await auth.loginEmail('user@example.test', 'fixture-password'); const epoch = auth.getAuthEpoch(); let changes = 0;
  auth.subscribeAuthChanges(() => { changes++; });
  const pending = auth.logout();
  assert.equal(auth.getAuthToken(), ''); assert.equal(auth.getAuthEpoch(), epoch + 1); assert.equal(changes, 1);
  await tick(); assert.equal(logoutCalls, 1); assert.equal(logoutHeaders.Authorization, 'Bearer canonical-account');
  server.resolve({ ok: true }); await pending;
});
