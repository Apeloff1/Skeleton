'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function load(relative, imports) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, relative), 'utf8'), { fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } });
  assert.equal(output.diagnostics.length, 0, relative + ' must compile');
  const module = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), relative + ': unexpected dependency ' + id); return imports[id];
  }, module, module.exports);
  return module.exports;
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function nodes(node) {
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(nodes);
  return [node, ...nodes(node.props?.children)];
}
function fixture() {
  let epoch = 0, principal = 'owner@example.test', cursor = 0;
  const slots = [], pendingEffects = [], observers = new Set(), calls = [], writes = [];
  const wire = {
    identity: async () => ({ tenantId: 'tenant-1', principalId: principal }),
    get: async url => {
      if (url.includes('/marketplace/mine')) return { ok: true, data: { listings: [{ playable_id: principal, title: 'Private listing', genre: 'arcade', price_usd: 1 }], totals: { games: 1, active: 1, sales: 2, revenue_usd: 7.5, plays: 3 } } };
      if (url.includes('/liveops/pass')) return { ok: true, data: { xp: 9, tier: 2, next_xp: 20, tiers: [{ tier: 2, reward: 'Anonymous activity reward' }] } };
      if (url.includes('/notifications/')) return { ok: true, data: { notifications: [{ appeal_id: principal, title: principal, status: 'denied' }] } };
      return { ok: true, data: { creators: [{ creator_id: principal, rank: 1, games: 1, sales: 2, plays: 3, revenue_usd: 7.5 }] } };
    },
    post: async () => ({ ok: true }),
  };
  const auth = { getAuthEpoch: () => epoch, resolveStorageTenantIdentity: () => wire.identity(),
    subscribeAuthChanges(fn) { observers.add(fn); return () => observers.delete(fn); } };
  const helper = load('src/product/creatorIdentity.ts', { '../auth/gameforgeAuth': auth });
  const element = (type, props, key) => ({ type, props: props || {}, key });
  const React = {
    useState(initial) { const i = cursor++; if (!slots[i]) slots[i] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[i].value, value => { slots[i].value = typeof value === 'function' ? value(slots[i].value) : value; writes.push(i); }]; },
    useRef(value) { const i = cursor++; if (!slots[i]) slots[i] = { current: value }; return slots[i]; },
    useCallback(fn, deps) { const i = cursor++, old = slots[i]; if (!old || deps.some((value, j) => !Object.is(value, old.deps[j]))) slots[i] = { value: fn, deps }; return slots[i].value; },
    useEffect(run, deps) { const i = cursor++, old = slots[i]; if (!old || deps.some((value, j) => !Object.is(value, old.deps[j]))) {
      const next = { deps, cleanup: old?.cleanup }; slots[i] = next; pendingEffects.push(() => { next.cleanup?.(); next.cleanup = run(); });
    } },
  };
  const api = { get: async (url, options) => { calls.push({ method: 'GET', url, options }); return wire.get(url, options); },
    post: async (url, body, options) => { calls.push({ method: 'POST', url, body, options }); return wire.post(url, body, options); } };
  const rn = Object.fromEntries(['View', 'Text', 'ScrollView', 'TouchableOpacity', 'ActivityIndicator', 'SafeAreaView', 'Image', 'RefreshControl'].map(key => [key, key]));
  rn.StyleSheet = { create: value => value, absoluteFill: {} };
  const router = { back() {}, push() {} }, haptics = { selection() {} };
  const Component = load('app/creator.tsx', {
    react: { __esModule: true, default: React }, 'react/jsx-runtime': { jsx: element, jsxs: element }, 'react-native': rn,
    'expo-router': { useRouter: () => router }, 'expo-linear-gradient': { LinearGradient: 'LinearGradient' }, 'expo-blur': { BlurView: 'BlurView' },
    '../src/utils/apiBase': { API_BASE: 'https://backend.test' }, '../src/utils/apiClient': { __esModule: true, default: api },
    '../src/hooks/useHaptics': { useHaptics: () => haptics }, '../src/utils/liveops': { getVisitorId: async () => 'v_anonymous_xp' },
    '../src/auth/gameforgeAuth': auth, '../src/product/creatorIdentity': helper,
    '../src/components/PrivateImage': { __esModule: true, default: 'PrivateImage' },
    '../src/theme/deluxe': { C: {}, S: {}, R: {} },
  }).default;
  return { wire, calls, writes, observers,
    render() { cursor = 0; return Component(); }, effects() { while (pendingEffects.length) pendingEffects.shift()(); },
    changeAccount(next = 'next@example.test') { epoch++; principal = next; for (const fn of observers) fn(); },
    unmount() { for (const slot of slots) if (slot?.cleanup) { slot.cleanup(); slot.cleanup = undefined; } },
  };
}
const find = (tree, id) => nodes(tree).find(node => node.props?.testID === id);
const refresh = tree => nodes(tree).find(node => node.type === 'ScrollView').props.refreshControl.props.onRefresh;

test('creator private reads use canonical principal while XP stays on its anonymous visitor', async () => {
  const f = fixture(); f.render(); f.effects(); await tick();
  const privateCalls = f.calls.filter(call => !call.url.includes('/liveops/pass'));
  assert.ok(privateCalls.some(call => call.url === '/api/marketplace/mine?creator_id=owner%40example.test'));
  assert.ok(privateCalls.some(call => call.url === '/api/governance/notifications/owner%40example.test'));
  assert.ok(privateCalls.every(call => !call.url.includes('v_anonymous_xp')));
  assert.equal(f.calls.find(call => call.url.includes('/liveops/pass')).url, '/api/liveops/pass?visitor_id=v_anonymous_xp');
  assert.ok(f.calls.every(call => call.options.signal instanceof AbortSignal));
  assert.ok(find(f.render(), 'cd-listing-owner@example.test')); f.unmount();
});

test('unknown account identity fails closed with a recoverable dashboard message', async () => {
  const f = fixture(); f.wire.identity = async () => { throw new Error('Unknown account'); };
  f.render(); f.effects(); await tick();
  assert.equal(f.calls.length, 0); assert.ok(find(f.render(), 'cd-error')); f.unmount();
});

test('account switch immediately resets dashboard payloads and rejects stale action closures', async () => {
  const f = fixture(); f.render(); f.effects(); await tick();
  const old = f.render(), dismiss = find(old, 'cd-notifs-dismiss').props.onPress, reload = refresh(old), count = f.calls.length;
  f.changeAccount();
  const cleared = f.render(); assert.equal(find(cleared, 'cd-listing-owner@example.test'), undefined); assert.equal(find(cleared, 'cd-appeal-notifs'), undefined);
  assert.ok(f.calls.slice(0, count).every(call => call.options.signal.aborted));
  await dismiss(); await reload(); assert.equal(f.calls.length, count);
  f.effects(); await tick(); const current = f.render();
  assert.ok(find(current, 'cd-listing-next@example.test')); assert.equal(find(current, 'cd-listing-owner@example.test'), undefined); f.unmount();
});

test('late native-ignore API reads cannot repaint private records after account change', async () => {
  const f = fixture(), pending = deferred(); f.wire.get = () => pending.promise;
  f.render(); f.effects(); await tick(); assert.equal(f.calls.length, 4); f.changeAccount();
  pending.resolve({ ok: true, data: { listings: [{ playable_id: 'old-private', title: 'Old private', genre: 'arcade', price_usd: 1 }], totals: { revenue_usd: 99 }, notifications: [{ appeal_id: 'old-private' }] } });
  await tick(); const tree = f.render(); assert.equal(find(tree, 'cd-listing-old-private'), undefined); assert.equal(find(tree, 'cd-appeal-notifs'), undefined); f.unmount();
});

test('notification acknowledgements use canonical identity and cannot clear the next account notification state', async () => {
  const f = fixture(); f.render(); f.effects(); await tick(); const pending = deferred(); f.wire.post = () => pending.promise;
  const acknowledging = find(f.render(), 'cd-notifs-dismiss').props.onPress(); await tick();
  assert.equal(f.calls.at(-1).url, '/api/governance/notifications/owner%40example.test/ack');
  f.changeAccount(); f.render(); f.effects(); await tick();
  assert.ok(find(f.render(), 'cd-appeal-notifs')); pending.resolve({ ok: true }); await acknowledging;
  assert.ok(find(f.render(), 'cd-appeal-notifs')); f.unmount();
});

test('unmount aborts pending identity resolution and detaches account observers', async () => {
  const f = fixture(), pending = deferred(); f.wire.identity = () => pending.promise;
  f.render(); f.effects(); f.unmount(); const writes = f.writes.length;
  pending.resolve({ tenantId: 'tenant-1', principalId: 'owner@example.test' }); await tick();
  assert.equal(f.calls.length, 0); assert.equal(f.writes.length, writes); assert.equal(f.observers.size, 0);
});
