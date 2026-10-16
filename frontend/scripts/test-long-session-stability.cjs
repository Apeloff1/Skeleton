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
      if (id === './requestRecoveryPolicy') return loadTS('utils/requestRecoveryPolicy.ts');
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
      states.push(typeof initial === 'function' ? initial() : initial);
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
    useMemo(fn) { return fn(); },
  };
  let cleanups = [];
  return {
    react,
    refs,
    get state() { return states[0]; },
    get states() { return states; },
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

test('thermal queue coalesces active work and maintains a finite pending queue', async t => {
  const { ThermalGuard } = loadTS('utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  let executions = 0;
  const first = guard.queue.enqueue('same', async () => { executions++; return 41; });
  const second = guard.queue.enqueue('same', async () => { executions++; return 99; });
  assert.equal(first, second, 'active and queued callers share one pending promise');
  assert.deepEqual(await Promise.all([first, second]), [41, 41]);
  assert.equal(executions, 1);

  const attempts = Array.from({ length: 260 }, (_, i) =>
    guard.queue.enqueue('unique-' + i, async () => i));
  guard.queue.flush();
  const statuses = await Promise.allSettled(attempts);
  assert.ok(statuses.some(item => item.status === 'rejected' &&
    /saturated/.test(item.reason.message)), 'queue must refuse work at capacity');
});

test('activity events are bounded even under sustained input bursts', t => {
  const { ThermalGuard } = loadTS('utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  for (let i = 0; i < 7000; i++) guard.recordActivity();
  assert.ok(guard.activity.events.length <= 2048);
});

test('storage hydration completes before chapter writes and never drops concurrent edits', async () => {
  const h = reactHarness();
  let resolveSaved;
  const persisted = [];
  const STORAGE_KEYS = {
    TUTORIAL_COMPLETED: 'tutorial', ADVANCED_UNLOCKED: 'advanced', BIBLE_PROGRESS: 'bible',
  };
  const storage = {
    getItem: key => key === 'bible'
      ? new Promise(resolve => { resolveSaved = resolve; })
      : Promise.resolve(null),
    setItem: async (key, value) => { persisted.push({ key, value }); },
  };
  const { useStorage } = loadTS('hooks/useStorage.ts', {
    react: h.react,
    '@react-native-async-storage/async-storage': storage,
    '../constants/config': { STORAGE_KEYS },
  });
  const hook = useStorage();
  h.mount();
  const first = hook.markChapterComplete('new-1');
  const second = hook.markChapterComplete('new-2');
  await settle();
  assert.equal(persisted.length, 0, 'never persist over unread authoritative data');
  resolveSaved(JSON.stringify({
    completedChapters: { saved: true }, bookmarks: ['saved-bookmark'], exerciseResults: {},
  }));
  await Promise.all([first, second]);
  const latest = JSON.parse(persisted.at(-1).value);
  assert.deepEqual(latest.completedChapters, { saved: true, 'new-1': true, 'new-2': true });
  assert.deepEqual(latest.bookmarks, ['saved-bookmark']);
  h.unmount();
});

test('storage save failures do not poison the serialized write queue', async () => {
  const h = reactHarness();
  let writes = 0;
  const storage = {
    getItem: async () => null,
    setItem: async () => { if (++writes === 1) throw new Error('disk full'); },
  };
  const { useStorage } = loadTS('hooks/useStorage.ts', {
    react: h.react,
    '@react-native-async-storage/async-storage': storage,
    '../constants/config': {
      STORAGE_KEYS: { TUTORIAL_COMPLETED: 'tutorial', ADVANCED_UNLOCKED: 'advanced', BIBLE_PROGRESS: 'bible' },
    },
  });
  const hook = useStorage();
  h.mount();
  await settle();
  const originalError = console.error;
  console.error = () => {};
  try {
    await hook.markChapterComplete('a');
    await hook.markChapterComplete('b');
    assert.equal(writes, 2, 'second write retries the latest full snapshot');
    assert.deepEqual(h.states[2].completedChapters, { a: true, b: true });
  } finally {
    console.error = originalError;
    h.unmount();
  }
});

test('interaction tasks reject on unmount and throwing callbacks reject their promises', async () => {
  const h = reactHarness();
  const metrics = {
    Dimensions: {
      get: () => ({ width: 400, height: 800 }),
      addEventListener: () => ({ remove() {} }),
    },
    PixelRatio: { get: () => 2, getFontScale: () => 1, roundToNearestPixel: n => n },
    Platform: { OS: 'android' },
  };
  const { useMobileOptimization } = loadTS('hooks/useMobileOptimization.ts', {
    react: h.react, 'react-native': metrics,
  });
  const hook = useMobileOptimization();
  h.mount();
  const bad = hook.runAfterInteraction(() => { throw new Error('render work failed'); });
  await assert.rejects(bad, /render work failed/);
  const a = hook.runAfterInteraction(() => 1);
  const b = hook.runAfterInteraction(() => 2);
  h.unmount();
  await assert.rejects(a, /Component unmounted/);
  await assert.rejects(b, /Component unmounted/);
});

test('a late session-start response cannot replace a newer session', async () => {
  const h = reactHarness();
  const pending = new Map();
  const service = {
    startSession: (_user, moduleId) => new Promise(resolve => pending.set(moduleId, resolve)),
    updateProgress: async () => ({ progress_updated: true, xp_earned: 0, new_achievements: [] }),
    logAIInteraction: async () => ({ logged: true }),
  };
  const { useSessionTracker } = loadTS('hooks/useSessionTracker.ts', {
    react: h.react, '../services/synergy': { synergyService: service },
  });
  const hook = useSessionTracker('person');
  h.mount();
  const older = hook.startSession('older');
  const newer = hook.startSession('newer');
  const response = module_id => ({
    session_started: true, module_id, emotional_context: {
      detected_emotion: 'neutral', stress_level: 0.2,
    }, content_adaptations: [], tips: [],
  });
  pending.get('newer')(response('newer'));
  await newer;
  pending.get('older')(response('older'));
  assert.equal(await older, null);
  assert.equal(h.states[0].moduleId, 'newer');
  h.unmount();
});

test('ending a session waits for pending progress then sends final progress once', async () => {
  const h = reactHarness();
  const updates = [];
  const service = {
    startSession: async (_user, moduleId) => ({
      session_started: true, module_id: moduleId,
      emotional_context: { detected_emotion: 'neutral', stress_level: 0.2 },
      content_adaptations: [], tips: [],
    }),
    updateProgress: (_user, moduleId, progress) => new Promise(resolve => {
      updates.push({ moduleId, progress, resolve });
    }),
    logAIInteraction: async () => ({ logged: true }),
  };
  const { useSessionTracker } = loadTS('hooks/useSessionTracker.ts', {
    react: h.react, '../services/synergy': { synergyService: service },
  });
  const hook = useSessionTracker('person');
  h.mount();
  await hook.startSession('book');
  const early = hook.updateProgress(10);
  await settle();
  assert.equal(updates.length, 1);
  await hook.updateProgress(20); // debounced while the first request is in flight
  const ending = hook.endSession();
  await settle();
  assert.equal(updates.length, 1, 'final write waits for in-flight update');
  updates[0].resolve({ progress_updated: true, xp_earned: 3, new_achievements: [] });
  await early;
  await settle();
  assert.equal(updates.length, 2);
  assert.deepEqual(updates.map(item => item.progress), [10, 20]);
  updates[1].resolve({ progress_updated: true, xp_earned: 0, new_achievements: [] });
  await ending;
  assert.equal(h.states[0].active, false);
  h.unmount();
});

test('mutation requests have one attempt on one host even when retry options are high', async () => {
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': {
      getItem: async () => null, setItem: async () => {},
    },
    './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: 'https://backup.test' },
  });
  const previous = global.fetch;
  const calls = [];
  global.fetch = async url => { calls.push(url); throw new Error('disconnected'); };
  try {
    await assert.rejects(net.resilientFetch('/make-game', {
      method: 'POST', body: { prompt: 'test' },
      retries: 500, hosts: ['https://backend.test', 'https://backup.test'],
    }), /after 1 attempts across 1 host/);
    assert.deepEqual(calls, ['https://backend.test/make-game']);
  } finally {
    global.fetch = previous;
    net.stopHeartbeat();
  }
});

test('authenticated read requests are not shared across credentials or cached', async () => {
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': {
      getItem: async () => null, setItem: async () => {},
    },
    './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: '' },
  });
  const previous = global.fetch;
  const calls = [];
  global.fetch = async (_url, options) => {
    const id = options.headers.Authorization;
    calls.push(id);
    return { ok: true, status: 200, headers: { get: () => null },
      text: async () => JSON.stringify({ id }) };
  };
  try {
    const [a, b] = await Promise.all([
      net.resilientFetch('/me', { headers: { Authorization: 'User-A' } }),
      net.resilientFetch('/me', { headers: { Authorization: 'User-B' } }),
    ]);
    assert.deepEqual([a.data.id, b.data.id], ['User-A', 'User-B']);
    assert.deepEqual(calls, ['User-A', 'User-B']);
    const repeated = await net.resilientFetch('/me', {
      headers: { Authorization: 'User-A' },
    });
    assert.equal(repeated.fromCache, false);
    assert.equal(calls.length, 3);
  } finally {
    global.fetch = previous;
    net.stopHeartbeat();
  }
});

test('oversized declared responses fail before reading or parsing', async () => {
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': {
      getItem: async () => null, setItem: async () => {},
    },
    './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: '' },
  });
  const previous = global.fetch;
  let bodyRead = false;
  global.fetch = async () => ({
    ok: true, status: 200,
    headers: { get: () => String(100 * 1024 * 1024) },
    text: async () => { bodyRead = true; return '{}'; },
  });
  try {
    await assert.rejects(net.resilientFetch('/huge', {
      retries: 0, cacheTtlMs: 0,
    }), /Response exceeds size budget/);
    assert.equal(bodyRead, false);
  } finally {
    global.fetch = previous;
    net.stopHeartbeat();
  }
});

test('aborted requests never initiate network activity', async () => {
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': {
      getItem: async () => null, setItem: async () => {},
    },
    './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: '' },
  });
  const previous = global.fetch;
  let called = false;
  global.fetch = async () => { called = true; throw new Error('unexpected'); };
  const controller = new AbortController();
  controller.abort();
  try {
    await assert.rejects(net.resilientFetch('/cancelled', {
      signal: controller.signal,
    }), /Request cancelled/);
    assert.equal(called, false);
  } finally {
    global.fetch = previous;
    net.stopHeartbeat();
  }
});

test('scoped heartbeats stop after the last subscriber but preserve an explicit owner', () => {
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': {
      getItem: async () => null, setItem: async () => {},
    },
    './apiBase': { API_BASE: '', API_FALLBACK_BASE: '' },
  });
  const previousSet = global.setTimeout;
  const previousClear = global.clearTimeout;
  const timers = [];
  global.setTimeout = (fn, delay) => {
    const entry = { fn, delay, cleared: false };
    timers.push(entry);
    return entry;
  };
  global.clearTimeout = handle => { handle.cleared = true; };
  try {
    const releaseA = net.retainHeartbeat();
    const releaseB = net.retainHeartbeat();
    assert.equal(timers.length, 1);
    releaseA();
    assert.equal(timers[0].cleared, false);
    releaseB();
    assert.equal(timers[0].cleared, true);
    releaseB(); // double dispose must be harmless
    net.startHeartbeat();
    const manual = timers.at(-1);
    const releaseC = net.retainHeartbeat();
    releaseC();
    assert.equal(manual.cleared, false, 'manual heartbeat owner remains');
    net.stopHeartbeat();
    assert.equal(manual.cleared, true);
  } finally {
    net.stopHeartbeat();
    global.setTimeout = previousSet;
    global.clearTimeout = previousClear;
  }
});

test('push registration after unmount never sets state or retains native listeners', async () => {
  const h = reactHarness();
  let resolvePermission;
  let removed = 0;
  let tokensRequested = 0;
  const notifications = {
    AndroidNotificationPriority: { HIGH: 4 },
    setNotificationHandler() {},
    addNotificationReceivedListener: () => ({ remove() { removed++; } }),
    addNotificationResponseReceivedListener: () => ({ remove() { removed++; } }),
    getPermissionsAsync: () => new Promise(resolve => { resolvePermission = resolve; }),
    requestPermissionsAsync: async () => ({ status: 'granted' }),
    getExpoPushTokenAsync: async () => { tokensRequested++; return { data: 'token' }; },
    setNotificationChannelAsync: async () => {},
    AndroidImportance: { MAX: 5 },
  };
  const { usePushNotifications } = loadTS('hooks/usePushNotifications.ts', {
    react: h.react,
    'react-native': { Platform: { OS: 'ios' } },
    'expo-device': { isDevice: true },
    'expo-notifications': notifications,
    'expo-constants': { easConfig: { projectId: 'configured-id' } },
    '@react-native-async-storage/async-storage': {
      getItem: async () => null, setItem: async () => {},
    },
  });
  usePushNotifications();
  h.mount();
  h.unmount();
  resolvePermission({ status: 'granted' });
  await settle();
  assert.equal(removed, 2);
  assert.equal(tokensRequested, 1);
  assert.equal(h.setters, 0);
});

test('rescheduling one reminder never cancels unrelated notifications', async () => {
  const cancelIds = [];
  let storedId = 'old-owned-id';
  const notifications = {
    AndroidNotificationPriority: { HIGH: 4 },
    SchedulableTriggerInputTypes: { TIME_INTERVAL: 'timeInterval' },
    setNotificationHandler() {},
    scheduleNotificationAsync: async () => 'new-owned-id',
    cancelScheduledNotificationAsync: async id => { cancelIds.push(id); },
  };
  const { scheduleDailyReminder } = loadTS('hooks/usePushNotifications.ts', {
    react: reactHarness().react,
    'react-native': { Platform: { OS: 'web' } },
    'expo-device': { isDevice: false },
    'expo-notifications': notifications,
    'expo-constants': {},
    '@react-native-async-storage/async-storage': {
      getItem: async () => storedId,
      setItem: async (_key, id) => { storedId = id; },
    },
  });
  await scheduleDailyReminder();
  assert.equal(storedId, 'new-owned-id');
  assert.deepEqual(cancelIds, ['old-owned-id']);
});

test('safe GET can retry a transient response without replaying mutations', async () => {
  const net = loadTS('utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': {
      getItem: async () => null, setItem: async () => {},
    },
    './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: '' },
  });
  let attempts = 0;
  const previous = global.fetch;
  global.fetch = async () => {
    attempts++;
    if (attempts === 1) return { ok: false, status: 429, text: async () => '' };
    return { ok: true, status: 200, headers: { get: () => null },
      text: async () => '{"ok":true}' };
  };
  try {
    const result = await net.resilientFetch('/retryable', {
      retries: 1, cacheTtlMs: 0,
    });
    assert.deepEqual(result.data, { ok: true });
    assert.equal(attempts, 2);
  } finally {
    net.stopHeartbeat();
    global.fetch = previous;
  }
});
