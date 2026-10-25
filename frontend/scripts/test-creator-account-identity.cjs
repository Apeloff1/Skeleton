'use strict';
// Real identity helper and screen callbacks; every API/browser seam is local.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function load(relative, imports) {
  const result = ts.transpileModule(fs.readFileSync(path.join(ROOT, relative), 'utf8'), {
    fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  });
  assert.equal(result.diagnostics.length, 0);
  const module = { exports: {} };
  compileFunction(result.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), relative + ': unexpected dependency ' + id);
    return imports[id];
  }, module, module.exports);
  return module.exports;
}
function identityFixture() {
  let epoch = 0, principal = 'creator+one@example.test', resolutions = 0;
  const observers = new Set();
  const wire = { identity: async () => ({ tenantId: 'tenant-1', principalId: principal }) };
  const owner = { getAuthEpoch: () => epoch, async resolveStorageTenantIdentity() { resolutions++; return wire.identity(); },
    subscribeAuthChanges(fn) { observers.add(fn); return () => observers.delete(fn); } };
  const helper = load('src/product/creatorIdentity.ts', { '../auth/gameforgeAuth': owner });
  return { ...helper, owner, wire, observers, resolutions: () => resolutions,
    change(next = 'creator+two@example.test') { principal = next; epoch++; for (const fn of observers) fn(); } };
}
function screenFixture(page) {
  const identity = identityFixture(), slots = [], effects = [], writes = [], calls = [], pushes = [], browserCalls = [];
  let cursor = 0, tree;
  const node = (type, props, key) => ({ type, props: props || {}, key });
  const same = (a, b) => a && b && a.length === b.length && a.every((value, i) => Object.is(value, b[i]));
  const React = {
    createElement(type, props, ...children) { return node(type, { ...props, children }); },
    useState(initial) { const i = cursor++; if (!slots[i]) slots[i] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[i].value, value => { slots[i].value = typeof value === 'function' ? value(slots[i].value) : value; writes.push(i); }]; },
    useRef(initial) { const i = cursor++; if (!slots[i]) slots[i] = { current: initial }; return slots[i]; },
    useCallback(fn, deps) { const i = cursor++; if (!slots[i] || !same(slots[i].deps, deps)) slots[i] = { value: fn, deps }; return slots[i].value; },
    useEffect(run, deps) { const i = cursor++, old = slots[i]; if (!old || !same(old.deps, deps)) {
      const next = { deps, cleanup: old?.cleanup }; slots[i] = next; effects.push(() => { next.cleanup?.(); next.cleanup = run(); });
    } },
  };
  const prefs = { genres: ['puzzle'], art_style: 'pixel', difficulty: 'balanced', tone: 'cozy', constitution: 'Private creator guidance', avoid: 'no gore' };
  const options = { art_styles: ['any', 'pixel'], difficulties: ['balanced'], tones: ['any', 'cozy'] };
  const wire = { get: async url => ({ ok: true, status: 200, data: url.includes('/preferences/') ? { preferences: { ...prefs, genres: [...prefs.genres] }, options }
    : url.includes('/purchases?') ? { purchases: [] } : { listings: [] } }),
  put: async () => ({ ok: true, status: 200 }), post: async () => ({ ok: true, data: { ok: true } }) };
  const api = {};
  for (const method of ['get', 'put', 'post']) api[method] = async (url, ...args) => {
    const body = method === 'get' ? undefined : args[0], requestOptions = args[method === 'get' ? 0 : 1];
    calls.push({ method, url, body, options: requestOptions }); return wire[method](url, body, requestOptions);
  };
  const router = { push(value) { pushes.push(value); }, back() {} }, haptics = { selection() {}, notify() {} };
  const rn = { Platform: { OS: 'ios' }, StyleSheet: { create: value => value, absoluteFill: {} } };
  for (const name of ['View', 'Text', 'ScrollView', 'TextInput', 'TouchableOpacity', 'ActivityIndicator', 'SafeAreaView', 'KeyboardAvoidingView', 'Image', 'Modal', 'RefreshControl']) rn[name] = name;
  const palette = new Proxy({}, { get: () => 8 });
  const Component = load('app/' + page + '.tsx', {
    react: { __esModule: true, default: React, ...React }, 'react/jsx-runtime': { jsx: node, jsxs: node },
    'react-native': rn, 'expo-router': { useRouter: () => router, useLocalSearchParams: () => ({}) },
    'expo-web-browser': { openBrowserAsync: async url => { browserCalls.push(url); } },
    '../src/utils/apiClient': { __esModule: true, default: api }, '../src/utils/apiBase': { API_BASE: 'https://backend.test' },
    '../src/auth/gameforgeAuth': identity.owner, '../src/product/creatorIdentity': identity,
    '../src/hooks/useHaptics': { useHaptics: () => haptics }, '../src/utils/liveops': { awardXp() { throw new Error('No purchase or XP operation is expected'); } },
    '../src/theme/deluxe': { C: palette, S: palette, R: palette },
    '../src/components/PrivateImage': { __esModule: true, default: 'PrivateImage' },
  }).default;
  function find(value, id) {
    if (!value || typeof value !== 'object') return null;
    if (Array.isArray(value)) { for (const child of value) { const got = find(child, id); if (got) return got; } return null; }
    if (value.props?.testID === id) return value;
    return find(value.props?.children, id);
  }
  function findType(value, type) {
    if (!value || typeof value !== 'object') return null;
    if (Array.isArray(value)) { for (const child of value) { const found = findType(child, type); if (found) return found; } return null; }
    if (value.type === type) return value;
    for (const child of Object.values(value.props || {})) { const found = findType(child, type); if (found) return found; }
    return null;
  }
  return { identity, wire, calls, pushes, browserCalls, prefs, writes,
    render() { cursor = 0; tree = Component(); return tree; },
    effects() { while (effects.length) effects.shift()(); },
    async settle() { for (let i = 0; i < 3; i++) { this.render(); this.effects(); await tick(); } return this.render(); },
    field(id) { const found = find(tree, id); assert.ok(found, 'Missing ' + id); return found.props; },
    refreshCallback() { const found = findType(tree, 'RefreshControl'); assert.ok(found, 'Missing real RefreshControl'); return found.props.onRefresh; },
    values: () => slots.filter(slot => Object.hasOwn(slot, 'value')).map(slot => slot.value),
    snapshot: () => JSON.stringify(tree),
    unmount() { for (const slot of slots) if (slot.cleanup) { slot.cleanup(); slot.cleanup = undefined; } },
  };
}

test('creator principal comes from the existing authenticated identity with no anonymous fallback', async () => {
  const f = identityFixture(); assert.equal(await f.resolveCreatorPrincipal(), 'creator+one@example.test');
  for (const principalId of ['', ' ', 'anonymous']) {
    f.wire.identity = async () => ({ tenantId: 'default', principalId }); await assert.rejects(f.resolveCreatorPrincipal(), /sign in/i);
  }
  f.wire.identity = async () => { throw new Error('Identity service unavailable'); };
  await assert.rejects(f.resolveCreatorPrincipal(), /unavailable/);
});

test('identity resolution is fenced before and after awaiting canonical owner state', async () => {
  for (const kind of ['account', 'abort']) {
    const f = identityFixture(), pending = deferred(), controller = new AbortController();
    f.wire.identity = () => pending.promise;
    const request = f.resolveCreatorPrincipal(controller.signal, 0);
    if (kind === 'account') f.change(); else controller.abort();
    pending.resolve({ tenantId: 'tenant-1', principalId: 'old@example.test' });
    await assert.rejects(request, /cancel/i);
  }
  const f = identityFixture(), controller = new AbortController(); controller.abort();
  await assert.rejects(f.resolveCreatorPrincipal(controller.signal), /cancel/i); assert.equal(f.resolutions(), 0);
  f.change(); await assert.rejects(f.resolveCreatorPrincipal(undefined, 0), /cancel/i); assert.equal(f.resolutions(), 0);
});

test('studio preferences read and write the canonical encoded owner and preview only a confirmed save', async () => {
  const f = screenFixture('studio-prefs'); await f.settle();
  assert.equal(f.calls[0].url, '/api/creator/preferences/creator%2Bone%40example.test');
  assert.equal(f.field('prefs-constitution').value, 'Private creator guidance');
  f.field('prefs-constitution').onChangeText('Updated private guidance'); f.render();
  await f.field('prefs-save').onPress();
  const write = f.calls.find(call => call.method === 'put');
  assert.equal(write.url, '/api/creator/preferences/creator%2Bone%40example.test');
  assert.equal(write.body.constitution, 'Updated private guidance'); assert.equal(write.options.signal.aborted, false);
  f.render(); f.wire.put = async () => ({ ok: false, status: 503 }); await f.field('prefs-preview').onPress();
  assert.deepEqual(f.pushes, []);
  f.render(); f.wire.put = async () => ({ ok: true }); await f.field('prefs-preview').onPress();
  assert.equal(f.pushes.length, 1); assert.ok(f.pushes[0].startsWith('/playable?brief=')); f.unmount();
});

test('studio preference account changes synchronously erase private state and reject stale actions', async () => {
  const f = screenFixture('studio-prefs'); await f.settle(); const staleSave = f.field('prefs-save').onPress;
  const initial = f.calls[0]; f.identity.change();
  assert.equal(initial.options.signal.aborted, true);
  assert.equal(f.values().some(value => value?.constitution === 'Private creator guidance'), false);
  await staleSave(); assert.equal(f.calls.filter(call => call.method === 'put').length, 0);
  await f.settle(); assert.ok(f.calls.some(call => call.url === '/api/creator/preferences/creator%2Btwo%40example.test'));
  f.unmount(); assert.equal(f.identity.observers.size, 0);
});

test('late preference loads and saves cannot replace a new account or navigate after logout', async () => {
  const f = screenFixture('studio-prefs'), pendingRead = deferred();
  f.wire.get = () => pendingRead.promise; f.render(); f.effects(); await tick();
  const oldRead = f.calls[0]; f.identity.change();
  f.wire.get = async () => ({ ok: true, data: { preferences: { ...f.prefs, constitution: 'Second account guidance' }, options: { art_styles: [], difficulties: [], tones: [] } } });
  await f.settle(); pendingRead.resolve({ ok: true, data: { preferences: f.prefs, options: { art_styles: [], difficulties: [], tones: [] } } }); await tick(); f.render();
  assert.equal(oldRead.options.signal.aborted, true); assert.equal(f.field('prefs-constitution').value, 'Second account guidance');
  const pendingWrite = deferred(); f.wire.put = () => pendingWrite.promise;
  const saving = f.field('prefs-preview').onPress(); await tick(); f.identity.change('creator+three@example.test');
  pendingWrite.resolve({ ok: true }); await saving; assert.deepEqual(f.pushes, []);
  assert.equal(f.values().some(value => value?.constitution === 'Second account guidance'), false); f.unmount();
});

test('unmounted preferences ignore a native adapter completing its private read late', async () => {
  const f = screenFixture('studio-prefs'), pending = deferred(); f.wire.get = () => pending.promise;
  f.render(); f.effects(); await tick(); f.unmount(); const count = f.writes.length;
  assert.equal(f.calls[0].options.signal.aborted, true);
  pending.resolve({ ok: true, data: { preferences: f.prefs, options: {} } }); await tick();
  assert.equal(f.writes.length, count);
});

test('marketplace private purchase queries and creator listing assertions use canonical identity', async () => {
  const f = screenFixture('marketplace'); await f.settle();
  assert.ok(f.calls.some(call => call.url === '/api/marketplace/purchases?buyer_id=creator%2Bone%40example.test'));
  f.field('mkt-sell').onPress(); f.render(); f.field('mkt-sell-id').onChangeText('owned-game'); f.render();
  await f.field('mkt-sell-submit').onPress();
  const listing = f.calls.find(call => call.url === '/api/marketplace/list');
  assert.equal(listing.body.creator_id, 'creator+one@example.test'); assert.equal(listing.body.playable_id, 'owned-game');
  assert.equal(listing.options.signal.aborted, false); f.unmount();
});

test('marketplace clears purchases and listing drafts on account changes and rejects late reads', async () => {
  const f = screenFixture('marketplace'), old = deferred();
  f.wire.get = async url => url.includes('/purchases?') ? old.promise : { ok: true, data: { listings: [] } };
  f.render(); f.effects(); await tick(); const oldRead = f.calls.find(call => call.url.includes('/purchases?'));
  f.field('mkt-sell').onPress(); f.render(); f.field('mkt-sell-id').onChangeText('old-private-game'); f.render();
  const staleListing = f.field('mkt-sell-submit').onPress;
  f.identity.change(); assert.equal(oldRead.options.signal.aborted, true);
  assert.equal(f.values().includes('old-private-game'), false); await staleListing();
  assert.equal(f.calls.some(call => call.method === 'post'), false);
  f.wire.get = async url => ({ ok: true, data: url.includes('/purchases?') ? { purchases: [] } : { listings: [] } });
  await f.settle(); old.resolve({ ok: true, data: { purchases: [{ playable_id: 'old-game', title: 'Private old purchase', genre: 'puzzle', price_usd: 1 }] } }); await tick(); f.render();
  assert.equal(f.snapshot().includes('Private old purchase'), false); f.unmount();
});

test('actual marketplace pull-to-refresh uses canonical purchases identity and fences stale account callbacks', async () => {
  const f = screenFixture('marketplace'); await f.settle();
  const refresh = f.refreshCallback(), before = f.calls.length;
  assert.doesNotThrow(() => refresh()); await tick();
  const requests = f.calls.slice(before);
  assert.ok(requests.some(call => call.url.startsWith('/api/marketplace/listings?')));
  assert.ok(requests.some(call => call.url === '/api/marketplace/purchases?buyer_id=creator%2Bone%40example.test'));
  f.identity.change(); const switched = f.calls.length;
  assert.doesNotThrow(() => refresh()); await tick(); assert.equal(f.calls.length, switched);
  await f.settle(); const current = f.calls.length;
  f.refreshCallback()(); await tick();
  assert.ok(f.calls.slice(current).some(call => call.url === '/api/marketplace/purchases?buyer_id=creator%2Btwo%40example.test'));
  f.unmount();
});

test('marketplace buyer identity is canonical and old checkout callbacks cannot open a browser', async () => {
  // This invokes only a local client seam. No payment service or HTTP call runs.
  const f = screenFixture('marketplace'), pending = deferred();
  f.wire.get = async url => ({ ok: true, data: url.includes('/purchases?') ? { purchases: [] }
    : { listings: [{ playable_id: 'game-to-buy', title: 'Local test game', genre: 'arcade', price_usd: 1 }] } });
  f.wire.post = () => pending.promise; await f.settle();
  const request = f.field('mkt-buy-game-to-buy').onPress(); await tick();
  const call = f.calls.find(value => value.url === '/api/marketplace/checkout');
  assert.equal(call.body.buyer_id, 'creator+one@example.test');
  f.identity.change(); assert.equal(call.options.signal.aborted, true);
  pending.resolve({ ok: true, data: { url: 'https://payment.invalid/never-open' } }); await request;
  assert.deepEqual(f.browserCalls, []); f.unmount();
});

test('a caller continuation checks the account again before submitting private preference writes', async () => {
  const f = screenFixture('studio-prefs'); await f.settle();
  const resolve = f.identity.resolveCreatorPrincipal;
  f.identity.resolveCreatorPrincipal = async (...args) => {
    const principal = await resolve(...args); queueMicrotask(() => f.identity.change()); return principal;
  };
  await f.field('prefs-save').onPress();
  assert.equal(f.calls.filter(call => call.method === 'put').length, 0); f.unmount();
});

function playableCallback(name) {
  const source = fs.readFileSync(path.join(ROOT, 'app/playable.tsx'), 'utf8');
  const syntax = ts.createSourceFile('playable.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let callback;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(syntax) === name && ts.isCallExpression(node.initializer)) callback = node.initializer.arguments[0].getText(syntax);
    ts.forEachChild(node, visit);
  }
  visit(syntax); assert.ok(callback, 'actual playable callback ' + name + ' must exist');
  const identity = identityFixture(), calls = [], writes = [], timers = [];
  const wire = { post: async () => ({ ok: false, data: {} }) };
  const module = { exports: {} };
  const output = ts.transpileModule('module.exports = (' + callback + ');', { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
  const setter = value => writes.push(value);
  compileFunction(output.outputText, ['module', 'api', 'game', 'haptics', 'appealReason', 'getAuthEpoch', 'resolveCreatorPrincipal',
    'creatorRequestCurrent', 'setReportBusy', 'setReportMsg', 'setReportModal', 'setAppealBusy', 'setAppealMsg', 'setAppealModal', 'setTimeout'])(
    module, { post: async (url, body, options) => { calls.push({ url, body, options }); return wire.post(url, body, options); } },
    { playable_id: 'owned-game' }, { selection() {} }, 'Please review the restriction on this original game', identity.owner.getAuthEpoch,
    (...args) => identity.resolveCreatorPrincipal(...args), identity.creatorRequestCurrent,
    setter, setter, setter, setter, setter, setter, fn => { timers.push(fn); return 1; });
  return { ...identity, identity, callback: module.exports, calls, writes, timers, wire };
}

test('actual playable report and appeal callbacks bind legacy identity fields to the authenticated principal', async () => {
  for (const [name, field, endpoint] of [['submitReport', 'reporter_id', '/api/governance/report'], ['submitAppeal', 'creator_id', '/api/governance/appeal']]) {
    const f = playableCallback(name); await f.callback('original-content concern');
    assert.equal(f.calls.length, 1); assert.equal(f.calls[0].url, endpoint);
    assert.equal(f.calls[0].body[field], 'creator+one@example.test');
    assert.equal(f.calls[0].body.playable_id, 'owned-game');
    const pending = deferred(); f.wire.post = () => pending.promise;
    const sending = f.callback('second concern'); await tick(); f.change(); const before = f.writes.length;
    pending.resolve({ ok: true, data: { appeal_id: 'must-not-surface' } }); await sending;
    assert.equal(f.writes.length, before); assert.equal(f.timers.length, 0);
  }
});

test('playable alias callbacks reject identity changes before their request continuation', async () => {
  for (const name of ['submitReport', 'submitAppeal']) {
    const f = playableCallback(name), resolve = f.identity.resolveCreatorPrincipal;
    f.identity.resolveCreatorPrincipal = async (...args) => {
      const principal = await resolve(...args); queueMicrotask(() => f.change()); return principal;
    };
    await f.callback('report concern'); assert.equal(f.calls.length, 0);
  }
});

test('actual playable screen keys private content to the canonical external auth epoch', () => {
  const identity = identityFixture(), snapshots = []; let subscribed = false;
  const React = { useSyncExternalStore(subscribe, getSnapshot, serverSnapshot) {
    assert.equal(subscribe, identity.owner.subscribeAuthChanges); assert.equal(getSnapshot, identity.owner.getAuthEpoch); assert.equal(serverSnapshot, getSnapshot);
    if (!subscribed) { subscribe(() => snapshots.push(getSnapshot())); subscribed = true; } return getSnapshot();
  } };
  const element = (type, props, key) => ({ type, props, key });
  const Screen = load('app/playable.tsx', {
    react: { __esModule: true, default: React }, 'react/jsx-runtime': { jsx: element, jsxs: element },
    'react-native': { Platform: { OS: 'ios' }, StyleSheet: { create: value => value } }, 'expo-clipboard': {}, 'expo-router': {},
    '../src/utils/apiBase': { API_BASE: 'https://backend.test' }, '../src/utils/apiClient': { __esModule: true, default: {} },
    '../src/components/PrivateImage': { __esModule: true, default: 'PrivateImage', savePrivateImage() {} },
    '../src/features/Playable/GamePreview': { __esModule: true, default: 'GamePreview' }, '../src/hooks/useHaptics': {},
    '../src/utils/safeStorage': {}, '../src/utils/liveops': { awardXp() {} }, '../src/auth/gameforgeAuth': identity.owner,
    '../src/product/creatorIdentity': identity, '../src/theme/tokens': { __esModule: true, default: {} },
  }).default;
  const first = Screen(); assert.equal(first.type.name, 'PlayableContent'); assert.equal(first.key, 0);
  identity.change(); const second = Screen(); assert.equal(second.type, first.type); assert.equal(second.key, 1);
  assert.deepEqual(snapshots, [1]);
});
