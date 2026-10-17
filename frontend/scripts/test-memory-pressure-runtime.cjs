'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function loadTS(name, mocks = {}) {
  const compiled = ts.transpileModule(fs.readFileSync(path.join(ROOT, name), 'utf8'), {
    fileName: name,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      esModuleInterop: true }, reportDiagnostics: true,
  });
  assert.equal(compiled.diagnostics.length, 0, name + ' parse');
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', compiled.outputText)(id => {
    assert.ok(Object.hasOwn(mocks, id), name + ': unexpected dependency ' + id);
    return mocks[id];
  }, mod, mod.exports);
  return mod.exports;
}
function guardFixture() {
  const events = [];
  let removed = 0;
  const mem = loadTS('utils/memoryGuard.ts', {
    'react-native': { AppState: { addEventListener: (name, callback) => {
      events.push({ name, callback });
      return { remove: () => { removed++; } };
    } } },
    './bootTracer': { traceStepSync() {} },
  });
  return { mem, events, get removed() { return removed; } };
}
test('pressure invokes all memory owners in spite of throwing observers', () => {
  const { mem } = guardFixture();
  let shed = 0, listener = 0;
  mem.registerMemoryShedder('throws', () => { throw new Error('broken renderer'); });
  mem.registerMemoryShedder('cache', () => shed++);
  mem.onMemoryPressure(() => { throw new Error('broken listener'); });
  mem.onMemoryPressure(() => listener++);
  mem.triggerMemoryPressure('os_warning');
  assert.equal(shed, 1);
  assert.equal(listener, 1);
  assert.equal(mem.memoryGuardStats().handlers, 2);
});
test('pressure debounce is bounded even if system clock moves backwards', () => {
  const { mem } = guardFixture();
  const original = Date.now;
  let now = 40_000;
  Date.now = () => now;
  let count = 0;
  mem.registerMemoryShedder('cache', () => count++);
  try {
    mem.triggerMemoryPressure('first');
    mem.triggerMemoryPressure('second');
    assert.equal(count, 1);
    now -= 60_000;
    mem.triggerMemoryPressure('clock_jump');
    assert.equal(count, 2);
    now += 4_000;
    mem.triggerMemoryPressure('another');
    assert.equal(count, 3);
  } finally { Date.now = original; }
});
test('reinstalling OS pressure guard is idempotent and uninstall frees listeners', () => {
  const f = guardFixture();
  f.mem.installMemoryGuard();
  f.mem.installMemoryGuard();
  assert.equal(f.events.filter(event => event.name === 'memoryWarning').length, 1);
  assert.equal(f.mem.memoryGuardStats().installed, true);
  f.mem.uninstallMemoryGuard();
  f.mem.uninstallMemoryGuard();
  assert.equal(f.removed, 1);
  assert.equal(f.mem.memoryGuardStats().installed, false);
  f.mem.installMemoryGuard();
  assert.equal(f.events.length, 2);
  f.mem.uninstallMemoryGuard();
});
test('memory owner registration has finite capacity and validates names', () => {
  const { mem } = guardFixture();
  for (let i = 0; i < 64; i++) mem.registerMemoryShedder('owner:' + i, () => {});
  assert.throws(() => mem.registerMemoryShedder('owner:overflow', () => {}), /full/);
  assert.throws(() => mem.registerMemoryShedder('../danger', () => {}), /Invalid/);
  assert.equal(mem.memoryGuardStats().handlers, 64);
});
test('unregistering an old memory handler does not remove the replacement', () => {
  const { mem } = guardFixture();
  const dropOld = mem.registerMemoryShedder('cache', () => { throw new Error('old'); });
  let result = 0;
  const dropNew = mem.registerMemoryShedder('cache', () => result++);
  dropOld();
  mem.triggerMemoryPressure('os');
  assert.equal(result, 1);
  dropNew();
  mem.triggerMemoryPressure('later');
  assert.equal(result, 1);
});
test('invalid stress inputs cannot corrupt render budgets', () => {
  const { mem } = guardFixture();
  for (const value of [NaN, Number.POSITIVE_INFINITY, -10, 0]) mem.bumpStress(value);
  assert.equal(mem.getStress(), 0);
  mem.reportFrameTime(Number.POSITIVE_INFINITY, 16);
  mem.reportFrameTime(0, 16);
  mem.reportFrameTime(100, Number.NaN);
  assert.equal(mem.getStress(), 0);
  mem.bumpStress(99);
  assert.equal(mem.getStress(), 3);
  const limits = mem.effectiveLimits();
  assert.ok(limits.maxMeshes > 0 && Number.isFinite(limits.frameMs));
});
test('sustained slow frames trigger stress but healthy frames do not', () => {
  const { mem } = guardFixture();
  for (let i = 0; i < 29; i++) mem.reportFrameTime(40, 16);
  assert.equal(mem.getStress(), 0);
  mem.reportFrameTime(40, 16);
  assert.equal(mem.getStress(), 1);
  for (let i = 0; i < 100; i++) mem.reportFrameTime(12, 16);
  assert.equal(mem.getStress(), 1);
});
test('thermal pressure purge does not instantiate an unused guard', () => {
  const thermal = loadTS('utils/thermalGuard.ts');
  thermal.purgeThermalCachesIfPresent();
  const guard = thermal.getThermalGuard();
  try {
    guard.cache.set('derived-image', 'x'.repeat(1000), 1000);
    assert.equal(guard.cache.size, 1);
    thermal.purgeThermalCachesIfPresent();
    assert.equal(guard.cache.size, 0);
  } finally { guard.destroy(); }
});
