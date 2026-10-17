'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const ROOT = path.resolve(__dirname, '..');
function loadTS(filename, mocks = {}) {
  const compilation = ts.transpileModule(fs.readFileSync(path.join(ROOT, filename), 'utf8'), {
    fileName: filename,
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
    reportDiagnostics: true,
  });
  assert.equal((compilation.diagnostics || []).length, 0, filename);
  const module = { exports: {} };
  new Function('require', 'module', 'exports', compilation.outputText)(
    id => {
      assert.ok(Object.hasOwn(mocks, id), 'unexpected import ' + id);
      return mocks[id];
    }, module, module.exports,
  );
  return module.exports;
}
function harness() {
  const effects = [];
  const states = [];
  const refs = [];
  let renders = 0;
  const react = {
    useState(initial) {
      const slot = states.length;
      states.push(typeof initial === 'function' ? initial() : initial);
      return [states[slot], next => {
        states[slot] = typeof next === 'function' ? next(states[slot]) : next;
        renders++;
      }];
    },
    useRef(initial) { const ref = { current: initial }; refs.push(ref); return ref; },
    useCallback(fn) { return fn; },
    useMemo(fn) { return fn(); },
    useEffect(fn) { effects.push(fn); },
  };
  let cleanup = [];
  return {
    react,
    states,
    refs,
    get updates() { return renders; },
    mount() { cleanup = effects.map(fn => fn()).filter(fn => typeof fn === 'function'); },
    unmount() { for (const fn of cleanup.reverse()) fn(); cleanup = []; },
  };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const starting = moduleId => ({
  session_started: true, module_id: moduleId,
  emotional_context: { detected_emotion: 'neutral', stress_level: 0 },
  content_adaptations: [], tips: [],
});

test('ending while start is pending invalidates the late response', async () => {
  const h = harness();
  let resolveStart;
  const service = {
    startSession: () => new Promise(resolve => { resolveStart = resolve; }),
    updateProgress: async () => ({ progress_updated: true, xp_earned: 0, new_achievements: [] }),
    logAIInteraction: async () => ({ logged: true }),
  };
  const { useSessionTracker } = loadTS('hooks/useSessionTracker.ts', {
    react: h.react, '../services/synergy': { synergyService: service },
  });
  const tracker = useSessionTracker('learner');
  h.mount();
  try {
    const started = tracker.startSession('chapter');
    await tracker.endSession();
    resolveStart(starting('chapter'));
    assert.equal(await started, null);
    assert.equal(h.states[0].active, false);
  } finally { h.unmount(); }
});

test('switching modules waits for prior final progress before starting the new one', async () => {
  const h = harness();
  const starts = [];
  const updates = [];
  let finish;
  const service = {
    startSession: async (_user, moduleId) => {
      starts.push(moduleId);
      return starting(moduleId);
    },
    updateProgress: (_user, moduleId, progress) => {
      updates.push({ moduleId, progress });
      return new Promise(resolve => { finish = resolve; });
    },
    logAIInteraction: async () => ({ logged: true }),
  };
  const { useSessionTracker } = loadTS('hooks/useSessionTracker.ts', {
    react: h.react, '../services/synergy': { synergyService: service },
  });
  const tracker = useSessionTracker('learner');
  h.mount();
  try {
    await tracker.startSession('A');
    // Avoid an additional immediate in-flight progress request.
    const switching = tracker.startSession('B');
    await settle();
    assert.deepEqual(starts, ['A'], 'B must not start until A finalizes');
    assert.equal(updates.length, 1);
    assert.equal(updates[0].moduleId, 'A');
    finish({ progress_updated: true, xp_earned: 0, new_achievements: [] });
    await switching;
    assert.deepEqual(starts, ['A', 'B']);
    assert.equal(h.states[0].moduleId, 'B');
  } finally { h.unmount(); }
});

test('racing session switches finalize the previous module only once', async () => {
  const h = harness();
  const starts = [];
  const updates = [];
  let finish;
  const service = {
    startSession: async (_u, moduleId) => {
      starts.push(moduleId);
      return starting(moduleId);
    },
    updateProgress: (_u, moduleId) => new Promise(resolve => {
      updates.push(moduleId);
      finish = resolve;
    }),
    logAIInteraction: async () => ({ logged: true }),
  };
  const { useSessionTracker } = loadTS('hooks/useSessionTracker.ts', {
    react: h.react, '../services/synergy': { synergyService: service },
  });
  const tracker = useSessionTracker('learner');
  h.mount();
  try {
    await tracker.startSession('A');
    const older = tracker.startSession('B');
    const newer = tracker.startSession('C');
    await settle();
    assert.deepEqual(updates, ['A']);
    finish({ progress_updated: true, xp_earned: 0, new_achievements: [] });
    assert.equal(await older, null);
    await newer;
    assert.deepEqual(starts, ['A', 'C']);
    assert.equal(h.states[0].moduleId, 'C');
  } finally { h.unmount(); }
});

test('unmount during module switching prevents any later local activation', async () => {
  const h = harness();
  let finish;
  const service = {
    startSession: async (_u, name) => starting(name),
    updateProgress: () => new Promise(resolve => { finish = resolve; }),
    logAIInteraction: async () => ({ logged: true }),
  };
  const { useSessionTracker } = loadTS('hooks/useSessionTracker.ts', {
    react: h.react, '../services/synergy': { synergyService: service },
  });
  const tracker = useSessionTracker('learner');
  h.mount();
  await tracker.startSession('A');
  const switching = tracker.startSession('B');
  await settle();
  const count = h.updates;
  h.unmount();
  finish({ progress_updated: true, xp_earned: 0, new_achievements: [] });
  assert.equal(await switching, null);
  assert.equal(h.updates, count);
});

test('concurrent reminder scheduling only installs one recurring alarm', async () => {
  let start;
  let scheduled = 0, saved = null;
  const notices = {
    AndroidNotificationPriority: { HIGH: 4 },
    SchedulableTriggerInputTypes: { TIME_INTERVAL: 'timeInterval' },
    setNotificationHandler() {},
    scheduleNotificationAsync: () => { scheduled++; return new Promise(resolve => { start = resolve; }); },
    cancelScheduledNotificationAsync: async () => {},
  };
  const { scheduleDailyReminder } = loadTS('hooks/usePushNotifications.ts', {
    react: harness().react,
    'react-native': { Platform: { OS: 'web' } },
    'expo-device': { isDevice: false },
    'expo-notifications': notices,
    'expo-constants': {},
    '@react-native-async-storage/async-storage': {
      getItem: async () => null,
      setItem: async (_k, value) => { saved = value; },
    },
  });
  const tasks = [scheduleDailyReminder(), scheduleDailyReminder(), scheduleDailyReminder()];
  assert.equal(scheduled, 0, 'storage read happens first');
  await settle();
  assert.equal(scheduled, 1);
  start('once');
  await Promise.all(tasks);
  assert.equal(saved, 'once');
  assert.equal(scheduled, 1);
});

test('failed reminder scheduling releases the singleflight lock', async () => {
  let schedules = 0;
  const notices = {
    AndroidNotificationPriority: { HIGH: 4 },
    SchedulableTriggerInputTypes: { TIME_INTERVAL: 'timeInterval' },
    setNotificationHandler() {},
    scheduleNotificationAsync: async () => {
      if (++schedules === 1) throw new Error('permission revoked');
      return 'recovered';
    },
    cancelScheduledNotificationAsync: async () => {},
  };
  let stored = null;
  const { scheduleDailyReminder } = loadTS('hooks/usePushNotifications.ts', {
    react: harness().react,
    'react-native': { Platform: { OS: 'web' } },
    'expo-device': { isDevice: false },
    'expo-notifications': notices,
    'expo-constants': {},
    '@react-native-async-storage/async-storage': {
      getItem: async () => stored,
      setItem: async (_k, val) => { stored = val; },
    },
  });
  await assert.rejects(scheduleDailyReminder(), /permission revoked/);
  await scheduleDailyReminder();
  assert.equal(schedules, 2);
  assert.equal(stored, 'recovered');
});

test('background power policy clamps timers to finite values', async () => {
  const h = harness();
  const handlers = {};
  const app = {
    currentState: 'background',
    addEventListener(_event, handler) {
      handlers.app = handler;
      return { remove() {} };
    },
  };
  const battery = {
    BatteryState: { CHARGING: 2, FULL: 5, DISCHARGING: 3 },
    getBatteryLevelAsync: async () => 0.8,
    getBatteryStateAsync: async () => 3,
    addBatteryLevelListener: () => ({ remove() {} }),
    addBatteryStateListener: () => ({ remove() {} }),
  };
  const { usePowerAwareness } = loadTS('hooks/usePowerAwareness.ts', {
    react: h.react, 'react-native': { AppState: app }, 'expo-battery': battery,
  });
  const power = usePowerAwareness();
  h.mount();
  try {
    assert.equal(power.getAnimationDuration(1000), 0);
    assert.ok(power.getPollingInterval(Number.POSITIVE_INFINITY) <= 300_000);
    assert.ok(power.getPollingInterval(-100) >= 60_000);
    assert.equal(power.getAnimationDuration(Number.NaN), 0);
    handlers.app('active');
    assert.equal(h.states[0].appState, 'active');
  } finally { h.unmount(); }
});

test('mobile throttle treats invalid limits as bounded and ignores work after unmount', () => {
  const h = harness();
  const { useMobileOptimization } = loadTS('hooks/useMobileOptimization.ts', {
    react: h.react,
    'react-native': {
      Dimensions: { get: () => ({ width: 400, height: 800 }), addEventListener: () => ({ remove() {} }) },
      PixelRatio: { getFontScale: () => 1, get: () => 2, roundToNearestPixel: n => n },
      Platform: { OS: 'android' },
    },
  });
  const ui = useMobileOptimization();
  h.mount();
  let calls = 0;
  ui.throttle(() => calls++, Number.POSITIVE_INFINITY);
  assert.equal(calls, 1);
  h.unmount();
  ui.throttle(() => calls++, 0);
  assert.equal(calls, 1);
});

test('session request timeout remains active while JSON parsing stalls', async () => {
  const { synergyService } = loadTS('services/synergy.ts', {
    '../utils/apiBase': { API_BASE: 'https://backend.test' },
  });
  const originalFetch = global.fetch;
  const originalSet = global.setTimeout;
  const originalClear = global.clearTimeout;
  const originalError = console.error;
  let fireTimeout, cleared = false, jsonStarted = false;
  global.setTimeout = fn => { fireTimeout = fn; return 900; };
  global.clearTimeout = () => { cleared = true; };
  global.fetch = async (_url, options) => ({
    ok: true, status: 200, headers: { get: () => null },
    json: () => new Promise((_resolve, reject) => {
      jsonStarted = true;
      options.signal.addEventListener('abort', () => reject(new Error('timeout during body')));
    }),
  });
  console.error = () => {};
  try {
    const work = synergyService.updateProgress('learner', 'chapter', 40, 10);
    await settle();
    assert.equal(jsonStarted, true);
    assert.equal(cleared, false);
    fireTimeout();
    const result = await work;
    assert.equal(result.progress_updated, false);
    assert.equal(cleared, true);
  } finally {
    global.fetch = originalFetch;
    global.setTimeout = originalSet;
    global.clearTimeout = originalClear;
    console.error = originalError;
  }
});

test('session service refuses declared oversized JSON before parsing', async () => {
  const { synergyService } = loadTS('services/synergy.ts', {
    '../utils/apiBase': { API_BASE: 'https://backend.test' },
  });
  const originalFetch = global.fetch;
  const originalError = console.error;
  let parsed = false;
  global.fetch = async () => ({
    ok: true, status: 200,
    headers: { get: () => String(5 * 1024 * 1024) },
    json: async () => { parsed = true; return {}; },
  });
  console.error = () => {};
  try {
    const result = await synergyService.updateProgress('learner', 'chapter', 40, 10);
    assert.equal(parsed, false);
    assert.equal(result.progress_updated, false);
  } finally {
    global.fetch = originalFetch;
    console.error = originalError;
  }
});
