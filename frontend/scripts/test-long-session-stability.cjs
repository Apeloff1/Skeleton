'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const ROOT = path.resolve(__dirname, '..');
function loadTS(filename, mocks = {}) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, filename), 'utf8'), {
    fileName: filename,
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
    reportDiagnostics: true,
  });
  assert.equal((output.diagnostics || []).length, 0, filename + ' syntax');
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', output.outputText)(
    id => {
      assert.ok(Object.hasOwn(mocks, id), filename + ': unexpected import ' + id);
      return mocks[id];
    }, mod, mod.exports,
  );
  return mod.exports;
}

function reactHarness() {
  const effects = [];
  const states = [];
  const refs = [];
  let setters = 0;
  let setting = false;
  const react = {
    useState(initial) {
      const slot = states.length;
      states.push(initial);
      return [initial, next => {
        assert.equal(setting, false, 'nested React state setter');
        setting = true;
        try {
          states[slot] = typeof next === 'function' ? next(states[slot]) : next;
          setters++;
        } finally { setting = false; }
      }];
    },
    useRef(initial) {
      const ref = { current: initial };
      refs.push(ref);
      return ref;
    },
    useEffect(fn) { effects.push(fn); },
    useCallback(fn) { return fn; },
  };
  let cleanups = [];
  return {
    react,
    refs,
    get state() { return states[0]; },
    get setters() { return setters; },
    mount() { cleanups = effects.map(fn => fn()).filter(fn => typeof fn === 'function'); },
    unmount() { for (const fn of cleanups.reverse()) fn(); cleanups = []; },
  };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test('thermal worker survives a synchronously throwing callback and releases capacity', async t => {
  const { ThermalGuard } = loadTS('utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  await assert.rejects(guard.queue.enqueue('bad', () => {
    throw new Error('synchronous failure');
  }), /synchronous failure/);
  const next = await Promise.race([
    guard.queue.enqueue('good', async () => 42),
    new Promise((_, reject) => setTimeout(() => reject(new Error('queue stalled')), 1200)),
  ]);
  assert.equal(next, 42);
  await settle();
  assert.equal(guard.queue.activeRequests, 0);
});

test('cooldown cancels an already-dequeued staggered request before side effects', async t => {
  const { ThermalGuard } = loadTS('utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  let calls = 0;
  const pending = guard.queue.enqueue('mutation', async () => { calls++; return 'done'; });
  guard.forceCooldown();
  await assert.rejects(pending, /Queue flushed/);
  assert.equal(calls, 0);
});

test('thermal background throttling survives battery updates, refresh and cooldown', t => {
  const { ThermalGuard } = loadTS('utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  guard.setAppBackground(true);
  guard.setBattery(0.8, true);
  assert.equal(guard.queue.currentDelay, 900);
  assert.equal(guard.queue.maxConcurrent, 1);
  guard.forceCooldown();
  assert.equal(guard.queue.currentDelay, 900);
  assert.equal(guard.queue.maxConcurrent, 1);
  guard.setAppBackground(false);
  assert.equal(guard.queue.currentDelay, 150);
});

test('power listeners use current battery observations without nested updates and dispose cleanly', async () => {
  const h = reactHarness();
  const handlers = {};
  let removals = 0;
  const battery = {
    BatteryState: { CHARGING: 2, FULL: 5, DISCHARGING: 3 },
    getBatteryLevelAsync: async () => 0.7,
    getBatteryStateAsync: async () => 3,
    addBatteryLevelListener: fn => { handlers.level = fn; return { remove() { removals++; } }; },
    addBatteryStateListener: fn => { handlers.charging = fn; return { remove() { removals++; } }; },
  };
  let appUnsub = false;
  const { usePowerAwareness } = loadTS('hooks/usePowerAwareness.ts', {
    react: h.react,
    'react-native': { AppState: { addEventListener: () => ({ remove() { appUnsub = true; } }) } },
    'expo-battery': battery,
  });
  usePowerAwareness();
  h.mount();
  await settle();
  assert.equal(h.state.batteryLevel, 0.7);
  handlers.level({ batteryLevel: 0.1 });
  assert.equal(h.state.performanceMode, 'powersaver');
  handlers.charging({ batteryState: 2 });
  assert.equal(h.state.batteryLevel, 0.1, 'charging must not overwrite level');
  assert.equal(h.state.performanceMode, 'high');
  handlers.level({ batteryLevel: -1 });
  assert.equal(h.state.batteryLevel, 0.1, 'unknown battery must not masquerade as 0%');
  h.unmount();
  assert.equal(removals, 2);
  assert.equal(appUnsub, true);
  const updates = h.setters;
  handlers.level({ batteryLevel: 0.5 });
  assert.equal(h.setters, updates);
});

test('unmount during power initialization never attaches late listeners', async () => {
  const h = reactHarness();
  let resolveLevel;
  let registrations = 0;
  const battery = {
    BatteryState: { CHARGING: 2, FULL: 5 },
    getBatteryLevelAsync: () => new Promise(resolve => { resolveLevel = resolve; }),
    getBatteryStateAsync: async () => 2,
    addBatteryLevelListener: () => { registrations++; return { remove() {} }; },
    addBatteryStateListener: () => { registrations++; return { remove() {} }; },
  };
  const { usePowerAwareness } = loadTS('hooks/usePowerAwareness.ts', {
    react: h.react,
    'react-native': { AppState: { addEventListener: () => ({ remove() {} }) } },
    'expo-battery': battery,
  });
  usePowerAwareness();
  h.mount();
  h.unmount();
  resolveLevel(0.2);
  await settle();
  assert.equal(registrations, 0);
  assert.equal(h.setters, 0);
});

test('stability recovery is single-flight, bounded and clean on unmount', async () => {
  const h = reactHarness();
  let alerts = 0;
  let removed = false;
  const { useStability } = loadTS('hooks/useStability.ts', {
    react: h.react,
    'react-native': { Alert: { alert() { alerts++; } } },
    '@react-native-community/netinfo': { addEventListener: () => () => { removed = true; } },
    '@react-native-async-storage/async-storage': {
      getItem: async () => null, setItem: async () => {}, removeItem: async () => {},
    },
  });
  const hook = useStability();
  h.mount();
  for (let i = 0; i < 5; i++) hook.handleError('failed');
  assert.equal(h.state.recoveryAttempts, 3);
  assert.equal(alerts, 1);
  assert.equal(await hook.attemptRecovery(async () => {}), false);
  hook.resetError();

  let complete;
  let calls = 0;
  const work = () => { calls++; return new Promise(resolve => { complete = resolve; }); };
  const first = hook.attemptRecovery(work);
  assert.equal(await hook.attemptRecovery(work), false);
  assert.equal(calls, 1);
  complete();
  assert.equal(await first, true);
  assert.equal(h.state.recoveryAttempts, 0);
  h.unmount();
  assert.equal(removed, true);
});

test('stability recovery refuses future-dated or malformed storage receipts', async () => {
  const h = reactHarness();
  let raw = JSON.stringify({ timestamp: Date.now() + 90_000, data: 'invalid' });
  const { useStability } = loadTS('hooks/useStability.ts', {
    react: h.react,
    'react-native': { Alert: { alert() {} } },
    '@react-native-community/netinfo': { addEventListener: () => () => {} },
    '@react-native-async-storage/async-storage': {
      getItem: async () => raw, setItem: async () => {}, removeItem: async () => {},
    },
  });
  const hook = useStability();
  h.mount();
  try {
    assert.equal(await hook.loadRecoveryState(), null);
    raw = JSON.stringify({ timestamp: 'never', data: 'invalid' });
    assert.equal(await hook.loadRecoveryState(), null);
    raw = JSON.stringify({ timestamp: Date.now() - 1000, data: { ok: true } });
    assert.deepEqual(await hook.loadRecoveryState(), { ok: true });
  } finally { h.unmount(); }
});

test('failed deduplicated GET does not leak an unhandled rejection', async () => {
  const storage = { getItem: async () => null, setItem: async () => {} };
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': storage,
    './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: '' },
  });
  const originalFetch = global.fetch;
  const unhandled = [];
  const onUnhandled = error => unhandled.push(error);
  process.on('unhandledRejection', onUnhandled);
  global.fetch = async () => { throw new Error('backend offline'); };
  try {
    await assert.rejects(net.resilientFetch('/unstable', {
      retries: 1, cacheTtlMs: 0, persist: false,
    }), /backend offline/);
    await settle();
    assert.deepEqual(unhandled, []);
  } finally {
    net.stopHeartbeat();
    global.fetch = originalFetch;
    process.off('unhandledRejection', onUnhandled);
  }
});

test('circuit reset cannot let an old request delete its replacement', async () => {
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': { getItem: async () => null, setItem: async () => {} },
    './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: '' },
  });
  const originalFetch = global.fetch;
  const resolvers = [];
  global.fetch = () => new Promise(resolve => { resolvers.push(resolve); });
  const reply = id => ({ ok: true, status: 200, text: async () => JSON.stringify({ id }) });
  try {
    const first = net.resilientFetch('/same-key', { retries: 1, cacheTtlMs: 0, persist: false });
    net.resetCircuit();
    const second = net.resilientFetch('/same-key', { retries: 1, cacheTtlMs: 0, persist: false });
    assert.equal(resolvers.length, 2);
    resolvers[0](reply('first'));
    await first;
    await settle();
    const third = net.resilientFetch('/same-key', { retries: 1, cacheTtlMs: 0, persist: false });
    assert.equal(resolvers.length, 2, 'the second request should still be coalesced');
    resolvers[1](reply('second'));
    assert.deepEqual((await second).data, { id: 'second' });
    assert.deepEqual((await third).data, { id: 'second' });
  } finally {
    net.stopHeartbeat();
    global.fetch = originalFetch;
  }
});

test('heartbeat stop/restart fences in-flight probes and their timers', async () => {
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': { getItem: async () => null, setItem: async () => {} },
    './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: '' },
  });
  const originalFetch = global.fetch;
  const originalSet = global.setTimeout;
  const originalClear = global.clearTimeout;
  const timers = [];
  let resolveFetch;
  global.setTimeout = (fn, delay) => {
    const timer = { fn, delay, cleared: false };
    timers.push(timer);
    return timer;
  };
  global.clearTimeout = timer => { timer.cleared = true; };
  global.fetch = () => new Promise(resolve => { resolveFetch = resolve; });
  try {
    net.startHeartbeat();
    net.startHeartbeat();
    assert.equal(timers.length, 1, 'only one heartbeat timer scheduled');
    timers[0].fn();
    assert.equal(timers.length, 2, 'in-flight probe has one timeout');
    net.stopHeartbeat();
    assert.equal(timers[1].cleared, false, 'timeout clears on settlement');
    net.startHeartbeat();
    assert.equal(timers.length, 3, 'restart schedules exactly one new generation');
    resolveFetch({ ok: true });
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(timers[1].cleared, true, 'old probe timeout was cleared');
    assert.equal(timers.length, 3, 'stale probe did not schedule another heartbeat');
  } finally {
    net.stopHeartbeat();
    global.fetch = originalFetch;
    global.setTimeout = originalSet;
    global.clearTimeout = originalClear;
  }
});
