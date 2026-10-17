'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

function fixture() {
  const output = ts.transpileModule(
    fs.readFileSync(path.join(__dirname, '../utils/safeTimers.ts'), 'utf8'),
    { fileName: 'safeTimers.ts', compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true,
    }, reportDiagnostics: true },
  );
  assert.equal(output.diagnostics.length, 0);
  let nextId = 0;
  const timers = new Map(), intervals = new Map();
  const old = {
    setTimeout: global.setTimeout, clearTimeout: global.clearTimeout,
    setInterval: global.setInterval, clearInterval: global.clearInterval,
  };
  global.setTimeout = (fn, ms) => {
    const id = ++nextId; timers.set(id, { fn, ms }); return id;
  };
  global.clearTimeout = id => { timers.delete(id); };
  global.setInterval = (fn, ms) => {
    const id = ++nextId; intervals.set(id, { fn, ms }); return id;
  };
  global.clearInterval = id => { intervals.delete(id); };
  let listener = null;
  let removals = 0;
  const app = {
    currentState: 'active',
    addEventListener(_event, fn) {
      listener = fn; return { remove() { removals++; listener = null; } };
    },
  };
  const effects = [];
  const react = {
    useRef: value => ({ current: value }),
    useEffect: fn => { effects.push(fn); },
  };
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', output.outputText)(id => {
    if (id === 'react') return react;
    if (id === 'react-native') return { AppState: app };
    throw new Error('Unexpected import ' + id);
  }, mod, mod.exports);
  return {
    clock: {
      timers, intervals,
      fireTimeout(id) {
        const task = timers.get(id);
        assert.ok(task);
        timers.delete(id);
        task.fn();
      },
      fireInterval(id) { assert.ok(intervals.has(id)); intervals.get(id).fn(); },
      advance(state) { app.currentState = state; listener?.(state); },
    },
    app, timers: mod.exports,
    effects,
    get removals() { return removals; },
    restore() {
      mod.exports.clearAllTimers();
      mod.exports.uninstallAppStateGuard();
      Object.assign(global, old);
    },
  };
}
const settle = () => new Promise(resolve => queueMicrotask(resolve));

test('one-shot timeout is removed before its callback and cannot leak', () => {
  const f = fixture();
  try {
    let calls = 0;
    f.timers.safeSetTimeout(() => calls++, 100);
    assert.equal(f.timers.liveTimerCount(), 1);
    f.clock.fireTimeout([...f.clock.timers.keys()][0]);
    assert.equal(calls, 1);
    assert.equal(f.timers.liveTimerCount(), 0);
  } finally { f.restore(); }
});

test('throwing timer callback cannot escape the runtime scheduler', () => {
  const f = fixture();
  const original = console.warn;
  console.warn = () => {};
  try {
    f.timers.safeSetTimeout(() => { throw new Error('screen disposed'); }, 100);
    f.clock.fireTimeout([...f.clock.timers.keys()][0]);
    assert.equal(f.timers.liveTimerCount(), 0);
  } finally { console.warn = original; f.restore(); }
});

test('native background pauses intervals without discarding their ownership', () => {
  const f = fixture();
  try {
    f.timers.installAppStateGuard();
    let ticks = 0;
    const cancel = f.timers.safeSetInterval(() => ticks++, 500);
    assert.equal(f.timers.safeTimerStats().armed, 1);
    f.clock.advance('background');
    assert.equal(f.timers.safeTimerStats().armed, 0);
    assert.equal(f.timers.safeTimerStats().suspended, 1);
    f.clock.advance('active');
    assert.equal(f.clock.intervals.size, 1);
    f.clock.fireInterval([...f.clock.intervals.keys()][0]);
    assert.equal(ticks, 1);
    cancel();
    assert.equal(f.timers.liveTimerCount(), 0);
  } finally { f.restore(); }
});

test('repeated foreground events never install overlapping interval timers', () => {
  const f = fixture();
  try {
    f.timers.installAppStateGuard();
    f.timers.safeSetInterval(() => {}, 1000);
    for (let i = 0; i < 100; i++) f.clock.advance('active');
    assert.equal(f.clock.intervals.size, 1);
    assert.equal(f.timers.liveTimerCount(), 1);
  } finally { f.restore(); }
});

test('a paused interval can be cancelled before foreground without resurrection', () => {
  const f = fixture();
  try {
    f.timers.installAppStateGuard();
    const cancel = f.timers.safeSetInterval(() => {}, 1000);
    f.clock.advance('inactive');
    cancel();
    f.clock.advance('active');
    assert.equal(f.clock.intervals.size, 0);
    assert.equal(f.timers.liveTimerCount(), 0);
  } finally { f.restore(); }
});

test('overlapping ticks skip a still-running asynchronous interval callback', async () => {
  const f = fixture();
  try {
    let finish, calls = 0;
    f.timers.safeSetInterval(() => { calls++; return new Promise(resolve => { finish = resolve; }); }, 100);
    const id = [...f.clock.intervals.keys()][0];
    f.clock.fireInterval(id);
    f.clock.fireInterval(id);
    assert.equal(calls, 1);
    finish();
    await settle(); await settle();
    f.clock.fireInterval(id);
    assert.equal(calls, 2);
  } finally { f.restore(); }
});

test('rejected asynchronous callbacks release busy status and never poison subsequent ticks', async () => {
  const f = fixture();
  const original = console.warn;
  console.warn = () => {};
  try {
    let rejectWork, calls = 0;
    f.timers.safeSetInterval(() => { calls++; return new Promise((_resolve, reject) => { rejectWork = reject; }); }, 100);
    const id = [...f.clock.intervals.keys()][0];
    f.clock.fireInterval(id);
    rejectWork(new Error('offline'));
    await settle(); await settle();
    f.clock.fireInterval(id);
    assert.equal(calls, 2);
  } finally { console.warn = original; f.restore(); }
});

test('registry capacity is hard bounded even under runaway registrations', () => {
  const f = fixture();
  const original = console.warn;
  console.warn = () => {};
  try {
    for (let i = 0; i < 1100; i++) f.timers.safeSetInterval(() => {}, 1000);
    assert.equal(f.timers.liveTimerCount(), 1000);
    assert.equal(f.clock.intervals.size, 1000);
  } finally { console.warn = original; f.restore(); }
});

test('timer-hook unmount cancels its pending timers and stops new callbacks', () => {
  const f = fixture();
  try {
    const hook = f.timers.useSafeTimers();
    const cleanup = f.effects.map(fn => fn()).filter(Boolean);
    hook.setTimeout(() => { throw new Error('must not execute'); }, 500);
    hook.setInterval(() => { throw new Error('must not execute'); }, 500);
    assert.equal(f.timers.liveTimerCount(), 2);
    for (const fn of cleanup) fn();
    assert.equal(f.timers.liveTimerCount(), 0);
    hook.setInterval(() => {}, 500);
    assert.equal(f.timers.liveTimerCount(), 0);
  } finally { f.restore(); }
});

test('completed hook timeouts are no longer retained in active registry', () => {
  const f = fixture();
  try {
    const hook = f.timers.useSafeTimers();
    const cleanup = f.effects.map(fn => fn()).filter(Boolean);
    for (let i = 0; i < 200; i++) {
      hook.setTimeout(() => {}, 1);
      f.clock.fireTimeout([...f.clock.timers.keys()][0]);
    }
    assert.equal(f.timers.liveTimerCount(), 0);
    for (const fn of cleanup) fn();
  } finally { f.restore(); }
});

test('guard install/uninstall releases the actual native subscription', () => {
  const f = fixture();
  try {
    f.timers.installAppStateGuard();
    f.timers.installAppStateGuard();
    f.timers.uninstallAppStateGuard();
    assert.equal(f.removals, 1);
    f.timers.installAppStateGuard();
    f.timers.uninstallAppStateGuard();
    assert.equal(f.removals, 2);
  } finally { f.restore(); }
});
