'use strict';
// Execute the real preview helper and component with controlled I/O/platform seams.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction, createContext, runInContext } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function load(relative, imports) {
  const result = ts.transpileModule(fs.readFileSync(path.join(ROOT, relative), 'utf8'), {
    fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  });
  assert.equal(result.diagnostics.length, 0, relative + ' must compile');
  const module = { exports: {} };
  compileFunction(result.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), relative + ': unexpected dependency ' + id);
    return imports[id];
  }, module, module.exports);
  return module.exports;
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function replace(t, name, value) {
  const old = global[name]; global[name] = value;
  t.after(() => { if (old === undefined) delete global[name]; else global[name] = old; });
}
function helperFixture(backend = 'https://backend.test') {
  let epoch = 0;
  const calls = [];
  const wire = { result: async () => ({ ok: true, status: 200, data: '<canvas id="game"></canvas>', error: null }) };
  const helper = load('src/product/playablePreview.ts', {
    '../utils/apiBase': { API_BASE: backend },
    '../auth/gameforgeAuth': { getAuthEpoch: () => epoch },
    '../utils/apiClient': { __esModule: true, default: { get: async (url, options) => {
      calls.push({ url, options }); return wire.result(url, options);
    } } },
  });
  return { ...helper, calls, wire, changeAccount() { epoch++; } };
}
function bootStorage(helper) {
  const generated = '<script>window.gameSawStorage=localStorage.getItem("high-score");</script><canvas></canvas>';
  const document = helper.preparePlayableDocument(generated);
  const bootstrap = /<script>([\s\S]*?)<\/script>/i.exec(document)?.[1];
  assert.ok(bootstrap, 'storage must be installed before any generated script');
  let nativeReads = 0;
  const context = createContext({ DOMException });
  context.window = context;
  for (const key of ['localStorage', 'sessionStorage']) Object.defineProperty(context, key, {
    configurable: true, get() { nativeReads++; throw new Error('Application storage must never be read'); },
  });
  runInContext(bootstrap, context, { timeout: 1000 });
  return { context, nativeReads: () => nativeReads, document, generated };
}

test('private raw preview loads only through the bounded canonical text transport', async () => {
  const f = helperFixture(); const controller = new AbortController();
  const result = await f.loadPlayableDocument('https://backend.test/api/playable/game_1-abc/raw', controller.signal);
  assert.equal(f.MAX_PLAYABLE_HTML_CHARS, 2 * 1024 * 1024);
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0].url, '/api/playable/game_1-abc/raw');
  assert.equal(f.calls[0].options.responseType, 'text');
  assert.equal(f.calls[0].options.maxResponseChars, f.MAX_PLAYABLE_HTML_CHARS);
  assert.equal(f.calls[0].options.retries, 0); assert.equal(f.calls[0].options.signal, controller.signal);
  assert.ok(f.calls[0].options.timeoutMs > 0 && f.calls[0].options.timeoutMs <= 15000);
  assert.ok(result.endsWith('<canvas id="game"></canvas>'));
});

test('raw URL validation rejects external, credential-bearing, queried and non-raw endpoints before I/O', async () => {
  const f = helperFixture();
  const rejected = [
    '', 'https://external.test/api/playable/game/raw', 'https://backend.test.evil.test/api/playable/game/raw',
    'https://backend.test:444/api/playable/game/raw', 'http://backend.test/api/playable/game/raw',
    'https://user:password@backend.test/api/playable/game/raw', '//external.test/api/playable/game/raw',
    '/api/v1/playable/game/raw', '/api/playable/game', '/api/playable/game/raw/extra',
    '/api/playable/game/raw?token=private', '/api/playable/game/raw#fragment',
    '/api/playable/a%2Fb/raw', '/api/playable/%2e%2e/raw', '/api/playable/' + 'a'.repeat(129) + '/raw',
    'javascript:alert(1)', 'data:text/html,private', 'file:///api/playable/game/raw',
  ];
  for (const uri of rejected) await assert.rejects(f.loadPlayableDocument(uri), undefined, uri);
  assert.equal(f.calls.length, 0);
});

test('raw loading honors a configured backend base path and accepts bounded IDs', async () => {
  const f = helperFixture('https://backend.test/product');
  await f.loadPlayableDocument('https://backend.test/product/api/playable/' + 'x'.repeat(128) + '/raw');
  assert.equal(f.calls[0].url, '/api/playable/' + 'x'.repeat(128) + '/raw');
  await assert.rejects(f.loadPlayableDocument('https://backend.test/api/playable/game/raw'));
  assert.equal(f.calls.length, 1);
});

test('cancelled and switched-account native responses cannot publish a private document', async () => {
  for (const cancel of ['signal', 'account']) {
    const f = helperFixture(), response = deferred(), controller = new AbortController();
    f.wire.result = () => response.promise;
    const request = f.loadPlayableDocument('/api/playable/game/raw', controller.signal);
    if (cancel === 'signal') controller.abort(); else f.changeAccount();
    response.resolve({ ok: true, status: 200, data: '<script>privateAccount();</script>' });
    await assert.rejects(request, /cancel/i);
  }
  const f = helperFixture(), controller = new AbortController(); controller.abort();
  await assert.rejects(f.loadPlayableDocument('/api/playable/game/raw', controller.signal), /cancel/i);
  assert.equal(f.calls.length, 0);
});

test('failed, non-text, empty and oversized responses never become playable documents', async () => {
  const f = helperFixture();
  for (const result of [
    { ok: false, status: 401, error: 'private internal credential detail' },
    { ok: false, status: 200, error: 'response_too_large' },
    { ok: true, status: 200, data: {} }, { ok: true, status: 200, data: '' },
    { ok: true, status: 200, data: 'x'.repeat(f.MAX_PLAYABLE_HTML_CHARS + 1) },
  ]) {
    f.wire.result = async () => result;
    await assert.rejects(f.loadPlayableDocument('/api/playable/game/raw'), error => !error.message.includes('credential detail'));
  }
});

test('document preamble enforces offline policy before all untrusted tags and preserves game code', () => {
  const f = helperFixture();
  const raw = '<!DOCTYPE html><head><base href="https://external.test/"><script>window.originalGame="🐉";</script></head><body><canvas></canvas></body>';
  const document = f.preparePlayableDocument(raw);
  assert.ok(document.endsWith(raw));
  const policy = /<meta http-equiv="Content-Security-Policy" content="([^"]+)">/i.exec(document);
  assert.ok(policy); assert.ok(document.indexOf(policy[0]) < document.indexOf('<script>'));
  for (const directive of ["default-src 'none'", "connect-src 'none'", "object-src 'none'", "frame-src 'none'", "base-uri 'none'", "form-action 'none'"]) assert.ok(policy[1].includes(directive), directive);
  assert.ok(document.indexOf('localStorage') < document.indexOf('window.originalGame'));
  for (const invalid of [null, undefined, 42, {}, '', ' \n\t', 'x'.repeat(f.MAX_PLAYABLE_HTML_CHARS + 1)]) assert.throws(() => f.preparePlayableDocument(invalid));
  assert.ok(f.preparePlayableDocument('x'.repeat(f.MAX_PLAYABLE_HTML_CHARS)).endsWith('x'.repeat(32)));
});

test('injected storage uses fresh isolated maps and never reads application storage', () => {
  const f = helperFixture(), a = bootStorage(f), b = bootStorage(f);
  const local = a.context.localStorage, session = a.context.sessionStorage;
  local.setItem('score', 42); local.setItem('__proto__', 'ordinary value');
  assert.equal(local.getItem('score'), '42'); assert.equal(local.getItem('__proto__'), 'ordinary value');
  assert.equal(local.length, 2); assert.equal(local.key(0), 'score'); assert.equal(local.key(99), null);
  assert.equal(session.getItem('score'), null); assert.equal(b.context.localStorage.getItem('score'), null);
  session.setItem('session-only', 'value'); local.removeItem('score');
  assert.equal(local.getItem('score'), null); local.clear(); assert.equal(local.length, 0);
  assert.equal(session.getItem('session-only'), 'value');
  assert.equal(a.nativeReads(), 0); assert.equal(b.nativeReads(), 0);
});

test('injected Storage key enumeration preserves a valid empty key', () => {
  const store = bootStorage(helperFixture()).context.localStorage;
  store.setItem('', 'empty key');
  assert.equal(store.key(0), ''); assert.equal(store.getItem(''), 'empty key');
});

test('storage entry, key, value and aggregate bounds reject without corrupting retained values', () => {
  const quota = fn => assert.throws(fn, error => error.name === 'QuotaExceededError');
  const store = bootStorage(helperFixture()).context.localStorage;
  store.setItem('k'.repeat(256), ''); quota(() => store.setItem('k'.repeat(257), ''));
  store.clear(); store.setItem('value', 'v'.repeat(16384)); quota(() => store.setItem('value', 'v'.repeat(16385)));
  assert.equal(store.getItem('value').length, 16384); store.clear();
  for (let i = 0; i < 128; i++) store.setItem('key-' + i, '');
  assert.equal(store.length, 128); quota(() => store.setItem('one-too-many', ''));
  store.setItem('key-0', 'updated'); assert.equal(store.getItem('key-0'), 'updated');
  store.clear();
  for (const key of ['a', 'b', 'c']) store.setItem(key, 'v'.repeat(16384));
  store.setItem('d', 'v'.repeat(16380)); quota(() => store.setItem('d', 'v'.repeat(16381)));
  assert.equal(store.getItem('d').length, 16380);
  store.removeItem('a'); store.setItem('e', 'v'.repeat(16384)); assert.equal(store.length, 4);
  store.clear(); store.setItem('after-clear', 'works'); assert.equal(store.length, 1);
});

test('frame error messages require this exact opaque frame and a bounded data shape', () => {
  const f = helperFixture(), frame = {}, valid = { __pl_error: true, message: 'Game failed' };
  assert.equal(f.playableMessage({ source: frame, origin: 'null', data: valid }, frame), 'Game failed');
  assert.equal(f.playableMessage({ source: frame, origin: 'null', data: { ...valid, message: 'line\ncontrol\u0000text\u007f' } }, frame), 'line control text ');
  for (const event of [
    { source: {}, origin: 'null', data: valid }, { source: frame, origin: 'https://backend.test', data: valid },
    { source: frame, origin: '', data: valid }, { source: null, origin: 'null', data: valid },
  ]) assert.equal(f.playableMessage(event, frame), null);
  assert.equal(f.playableMessage({ source: null, origin: 'null', data: valid }, null), null);
  for (const data of [null, '', [], true, valid.message, { __pl_error: 'true', message: 'x' },
    { __pl_error: true, message: 42 }, { __pl_error: true, message: '' }, { __pl_error: true, message: 'x'.repeat(1001) }]) {
    assert.equal(f.playableMessage({ source: frame, origin: 'null', data }, frame), null);
  }
  assert.equal(f.playableMessage({ source: frame, origin: 'null', data: { ...valid, message: 'x'.repeat(1000) } }, frame).length, 1000);
  assert.equal(f.playableMessage({ source: {}, origin: 'null', get data() { throw new Error('foreign data accessed'); } }, frame), null);
});

test('native navigation accepts only its isolated document bootstrap origin', () => {
  const f = helperFixture();
  assert.equal(f.playableNativeNavigation('about:blank'), true);
  assert.equal(f.playableNativeNavigation(f.PLAYABLE_NATIVE_ORIGIN), true);
  for (const url of ['https://backend.test/', 'https://external.test/', 'https://playable.invalid/other', 'file:///private', 'javascript:alert(1)', 'data:text/html,content']) assert.equal(f.playableNativeNavigation(url), false);
  assert.equal(f.PLAYABLE_FRAME_SANDBOX.split(/\s+/).includes('allow-same-origin'), false);
  assert.equal(f.PLAYABLE_FRAME_SANDBOX.split(/\s+/).includes('allow-top-navigation'), false);
});

test('actual API text mode preserves JSON-looking documents and separates typed cache entries', async t => {
  const policy = load('src/utils/requestRecoveryPolicy.ts', {}), rows = new Map(); let fetches = 0;
  const owner = { getAuthToken: () => '', getAuthEpoch: () => 0, initializeStoredToken: async () => {}, subscribeAuthChanges: () => () => {} };
  const api = load('src/utils/apiClient.ts', {
    './apiBase': { API_BASE: 'https://backend.test' }, './requestRecoveryPolicy': policy,
    './breadcrumbs': { trail: { add() {} } }, './bootTracer': { traceStep: async () => {} },
    '../foundation/queryCache': { appQueryCache: { clear() {} } }, '../auth/gameforgeAuth': owner,
  }).default;
  replace(t, 'sessionStorage', { get length() { return rows.size; }, key: i => [...rows.keys()][i] ?? null,
    getItem: key => rows.get(key) ?? null, setItem: (key, value) => rows.set(key, value), removeItem: key => rows.delete(key) });
  replace(t, 'fetch', async () => { fetches++; return new Response('{}', { headers: { 'content-type': 'text/html' } }); });
  const opts = { cacheKey: 'same-preview', retries: 0 };
  assert.deepEqual((await api.get('/api/playable/game/raw', opts)).data, {});
  assert.equal((await api.get('/api/playable/game/raw', { ...opts, responseType: 'text' })).data, '{}');
  assert.equal((await api.get('/api/playable/game/raw', { ...opts, responseType: 'text' })).data, '{}');
  assert.deepEqual((await api.get('/api/playable/game/raw', opts)).data, {});
  assert.equal(fetches, 2);
});

function componentFixture(t, platform = 'web') {
  const helper = helperFixture(), slots = [], pendingEffects = [], requests = [], observers = new Set(), listeners = new Set(), reports = [], writes = [];
  let cursor = 0, props = { uri: '/api/playable/first/raw', testID: 'private-preview', onGameError: message => reports.push(message) };
  const element = (type, input, key) => ({ type, props: input || {}, key });
  const React = {
    createElement(type, input, ...children) { return element(type, { ...input, ...(children.length ? { children } : {}) }); },
    useState(initial) { const i = cursor++; if (!slots[i]) slots[i] = { value: initial };
      return [slots[i].value, value => { slots[i].value = typeof value === 'function' ? value(slots[i].value) : value; writes.push(i); }]; },
    useRef(initial) { const i = cursor++; if (!slots[i]) slots[i] = { current: initial }; return slots[i]; },
    useEffect(run, deps) { const i = cursor++, old = slots[i];
      if (!old || deps.some((value, j) => !Object.is(value, old.deps[j]))) {
        const next = { deps, cleanup: old?.cleanup }; slots[i] = next;
        pendingEffects.push(() => { next.cleanup?.(); next.cleanup = run(); });
      }
    },
  };
  const window = { addEventListener(type, fn) { if (type === 'message') listeners.add(fn); }, removeEventListener(_type, fn) { listeners.delete(fn); } };
  replace(t, 'window', window);
  const Native = function NativePreviewFixture() {};
  const Component = load('src/features/Playable/GamePreview.tsx', {
    react: { __esModule: true, default: React }, 'react/jsx-runtime': { jsx: element, jsxs: element },
    'react-native': { Platform: { OS: platform }, View: 'View', Text: 'Text', ActivityIndicator: 'ActivityIndicator' },
    'react-native-webview': { WebView: Native },
    '../../auth/gameforgeAuth': { subscribeAuthChanges(fn) { observers.add(fn); return () => observers.delete(fn); } },
    '../../product/playablePreview': { ...helper, loadPlayableDocument(uri, signal) {
      const response = deferred(); requests.push({ uri, signal, ...response }); return response.promise;
    } },
  }).default;
  return { requests, reports, writes, observers, listeners, Native,
    render(next = {}) { props = { ...props, ...next }; cursor = 0; return Component(props); },
    effects() { while (pendingEffects.length) pendingEffects.shift()(); },
    accountChange() { for (const fn of observers) fn(); },
    unmount() { for (const slot of slots) if (slot?.cleanup) { slot.cleanup(); slot.cleanup = undefined; } },
    attach(node) {
      assert.ok(node.props.ref);
      const target = platform === 'web' ? { style: { visibility: 'visible' }, srcdoc: node.props.srcDoc, src: 'about:srcdoc', contentWindow: {} }
        : { stopped: 0, injected: [], stopLoading() { this.stopped++; }, injectJavaScript(value) { this.injected.push(value); } };
      node.props.ref.current = target; return target;
    },
  };
}

test('account changes clear visible web bytes immediately and fence queued frame errors', async t => {
  const f = componentFixture(t); f.render(); f.effects();
  f.requests[0].resolve('<canvas>private first account</canvas>'); await tick();
  const node = f.render(), frame = f.attach(node); f.effects();
  assert.equal(node.type, 'iframe'); assert.equal(node.props.src, undefined); assert.ok(node.props.srcDoc.includes('private first account'));
  const queued = [...f.listeners][0]; assert.ok(queued);
  f.accountChange();
  assert.equal(f.requests[0].signal.aborted, true); assert.equal(frame.srcdoc, '');
  assert.equal(frame.src, 'about:blank'); assert.equal(frame.style.visibility, 'hidden');
  queued({ source: frame.contentWindow, origin: 'null', data: { __pl_error: true, message: 'stale account error' } });
  assert.deepEqual(f.reports, []); assert.equal(f.render().type, 'View'); f.effects(); f.unmount();
  assert.equal(f.observers.size, 0); assert.equal(f.listeners.size, 0);
});

test('URI replacement and unmount discard deferred native-ignore loader completions', async t => {
  const f = componentFixture(t); f.render(); f.effects();
  f.render({ uri: '/api/playable/second/raw' }); f.effects();
  assert.equal(f.requests[0].signal.aborted, true); assert.equal(f.requests.length, 2);
  f.requests[1].resolve('<canvas>current second game</canvas>'); await tick();
  let node = f.render(); assert.equal(node.props.srcDoc, '<canvas>current second game</canvas>');
  f.requests[0].resolve('<canvas>late first game</canvas>'); await tick();
  node = f.render(); assert.equal(node.props.srcDoc, '<canvas>current second game</canvas>');
  const frame = f.attach(node); f.effects(); f.unmount();
  assert.equal(f.requests[1].signal.aborted, true); assert.equal(frame.srcdoc, '');
  assert.equal(f.observers.size, 0); assert.equal(f.listeners.size, 0);
  const pending = componentFixture(t); pending.render(); pending.effects(); pending.unmount(); const before = pending.writes.length;
  pending.requests[0].resolve('<canvas>must not mount after unmount</canvas>'); await tick();
  assert.equal(pending.writes.length, before);
});

test('account switch while loading cannot mount a late private document', async t => {
  const f = componentFixture(t); f.render(); f.effects(); f.accountChange();
  f.requests[0].resolve('<canvas>late private account</canvas>'); await tick();
  assert.equal(f.render().type, 'View'); assert.equal(f.requests[0].signal.aborted, true); f.effects(); f.unmount();
});

test('native previews use an isolated HTML origin, disable shared state, and fence old bridge callbacks', async t => {
  const f = componentFixture(t, 'ios'); f.render(); f.effects(); f.requests[0].resolve('<canvas>native first</canvas>'); await tick();
  const old = f.render(), native = f.attach(old); f.effects();
  assert.equal(old.type, f.Native); assert.equal(old.props.source.html, '<canvas>native first</canvas>');
  assert.equal(old.props.source.uri, undefined); assert.equal(old.props.source.baseUrl, 'https://playable.invalid/');
  for (const prop of ['domStorageEnabled', 'cacheEnabled', 'sharedCookiesEnabled', 'thirdPartyCookiesEnabled', 'allowFileAccess',
    'allowFileAccessFromFileURLs', 'allowUniversalAccessFromFileURLs', 'setSupportMultipleWindows', 'javaScriptCanOpenWindowsAutomatically']) assert.equal(old.props[prop], false, prop);
  assert.equal(old.props.incognito, true); assert.equal(old.props.mixedContentMode, 'never');
  assert.equal(old.props.onShouldStartLoadWithRequest({ url: 'about:blank' }), true);
  assert.equal(old.props.onShouldStartLoadWithRequest({ url: 'https://backend.test/api/private' }), false);
  f.render({ uri: '/api/playable/second/raw' }); f.effects();
  assert.equal(native.stopped, 1); assert.ok(native.injected.some(value => value.includes('document.close')));
  f.requests[1].resolve('<canvas>native second</canvas>'); await tick(); const current = f.render(); f.attach(current); f.effects();
  assert.notEqual(current.key, old.key);
  old.props.onMessage({ nativeEvent: { data: '{"__pl_error":true,"message":"old private error"}' } });
  assert.deepEqual(f.reports, []);
  current.props.onMessage({ nativeEvent: { data: '{"__pl_error":true,"message":"current game error"}' } });
  assert.deepEqual(f.reports, ['current game error']);
  f.accountChange(); current.props.onMessage({ nativeEvent: { data: '{"__pl_error":true,"message":"after logout"}' } });
  assert.deepEqual(f.reports, ['current game error']); assert.equal(f.render().type, 'View'); f.effects(); f.unmount();
});
