'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../services/monthCycleForeground.ts'), 'utf8');
const output = ts.transpileModule(code, {
  fileName: 'monthCycleForeground.ts', compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
    esModuleInterop: true,
  }, reportDiagnostics: true,
});
assert.equal(output.diagnostics.length, 0);
const mod = { exports: {} };
new Function('require','module','exports',output.outputText)(id => {
  if (id === './monthCycleRecovery') return {};
  throw new Error('Unexpected dependency: '+id);
},mod,mod.exports);
const { MonthCycleForegroundDriver } = mod.exports;
const tick = () => new Promise(resolve => setImmediate(resolve));
function fixture({ initial = 'active', execute = async () => ({
  attempted: 0, stillRunning: 0, disconnected: 0,
  terminalObserved: 0, skipped: 0, interrupted: false,
}) } = {}) {
  const originalSet = global.setTimeout, originalClear = global.clearTimeout;
  let counter = 0, listener, unsubscribed = 0, stopped = 0;
  const timers = new Map();
  global.setTimeout = (fn, ms) => {
    const id = ++counter;
    timers.set(id, { fn, ms });
    return id;
  };
  global.clearTimeout = id => { timers.delete(id); };
  const platform = {
    currentState: initial,
    addEventListener(_kind, cb) {
      listener = cb;
      return { remove() { listener = null; unsubscribed++; } };
    },
  };
  let calls = 0;
  const recovery = {
    reconcileDue: () => { calls++; return execute(); },
    stop: () => { stopped++; },
  };
  return {
    platform, recovery, timers,
    change(value) { platform.currentState = value; listener?.(value); },
    fire(delay) {
      const item = [...timers].find(([, value]) => value.ms === delay);
      assert.ok(item, 'missing expected timer '+delay);
      timers.delete(item[0]);
      item[1].fn();
    },
    get calls() { return calls; },
    get stopped() { return stopped; },
    get unsubscribed() { return unsubscribed; },
    restore() {
      global.setTimeout = originalSet;
      global.clearTimeout = originalClear;
    },
  };
}
test('cold foreground start schedules exactly one immediate bounded pass', async () => {
  const f = fixture();
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery);
  try {
    driver.start();
    assert.equal(f.timers.size, 1);
    f.fire(0); await tick();
    assert.equal(f.calls, 1);
    assert.equal(f.timers.size, 1);
    assert.equal([...f.timers.values()][0].ms, 15 * 60_000);
  } finally { driver.dispose(); f.restore(); }
});
test('inactive startup leaves the scheduler dormant until visible', async () => {
  const f = fixture({ initial: 'background' });
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery);
  try {
    driver.start();
    assert.equal(f.timers.size, 0);
    f.change('active');
    assert.equal(f.timers.size, 1);
    f.fire(0); await tick();
    assert.equal(f.calls, 1);
  } finally { driver.dispose(); f.restore(); }
});
test('background cancels owned timers and interrupts the current pass', () => {
  const f = fixture();
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery);
  try {
    driver.start();
    f.change('background');
    assert.equal(f.timers.size, 0);
    assert.equal(f.stopped, 1);
    assert.equal(f.calls, 0);
  } finally { driver.dispose(); f.restore(); }
});
test('a rapid stream of duplicate foreground events never multiplies timers', () => {
  const f = fixture();
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery);
  try {
    driver.start();
    for (let i=0;i<200;i++) f.change('active');
    assert.equal(f.timers.size, 1);
  } finally { driver.dispose(); f.restore(); }
});
test('late finish from an inactive generation never fires stale reporting hooks', async () => {
  let finish;
  const f = fixture({ execute: () => new Promise(resolve => { finish = resolve; }) });
  let reports = 0;
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery, {
    onReport: () => { reports++; },
  });
  try {
    driver.start(); f.fire(0); await tick();
    f.change('background');
    finish({ attempted: 1 });
    await tick();
    assert.equal(reports, 0);
    assert.equal(f.timers.size, 0);
  } finally { driver.dispose(); f.restore(); }
});
test('background-to-foreground bounce creates one immediate follow-up after old pass', async () => {
  let finish;
  const f = fixture({ execute: () => new Promise(resolve => { finish = resolve; }) });
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery);
  try {
    driver.start(); f.fire(0); await tick();
    f.change('background');
    f.change('active');
    f.fire(0); await tick();
    assert.equal(f.calls, 1);
    finish({ attempted: 0 });
    await tick();
    assert.ok([...f.timers.values()].some(t => t.ms === 0));
  } finally { driver.dispose(); f.restore(); }
});
test('explicit disposal releases platform listener and stops all subsequent observation', async () => {
  const f = fixture();
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery);
  try {
    const close = driver.start();
    close();
    close();
    assert.equal(f.unsubscribed, 1);
    assert.equal(f.timers.size, 0);
    f.change('active');
    assert.equal(f.calls, 0);
    assert.throws(() => driver.start(), /disposed/);
  } finally { driver.dispose(); f.restore(); }
});
test('observer failures are isolated and the next cadence remains armed', async () => {
  const f = fixture();
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery, {
    onReport: () => { throw new Error('unmounted view'); },
    cadenceMs: 100,
  });
  try {
    driver.start();
    f.fire(0); await tick();
    assert.equal([...f.timers.values()][0].ms, 60_000);
    f.fire(60_000); await tick();
    assert.equal(f.calls, 2);
  } finally { driver.dispose(); f.restore(); }
});
test('errors in durable observation report failure without runaway immediate retry', async () => {
  const f = fixture({ execute: async () => { throw new Error('disk locked'); } });
  let errors = 0;
  const driver = new MonthCycleForegroundDriver(f.platform, f.recovery, {
    onError: () => { errors++; },
  });
  try {
    driver.start(); f.fire(0); await tick();
    assert.equal(errors, 1);
    assert.equal([...f.timers.values()][0].ms, 15 * 60_000);
  } finally { driver.dispose(); f.restore(); }
});
