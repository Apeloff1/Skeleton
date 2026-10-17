'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/utils/useNetworkStatus.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  reportDiagnostics: true,
});
assert.equal(compiled.diagnostics.length, 0);
function hookFixture() {
  const effects = [], state = [];
  let listener;
  const timers = new Map();
  let next = 0;
  const react = {
    useEffect(fn) { effects.push(fn); },
    useRef(value) { return { current: value }; },
    useState(initial) {
      state.push(typeof initial === 'function' ? initial() : initial);
      return [state[0], value => { state[0] = value; }];
    },
  };
  const native = { AppState: { currentState: 'active',
    addEventListener(_type, callback) { listener = callback; return { remove() { listener = null; } }; },
  } };
  const oldTimeout = global.setTimeout, oldClear = global.clearTimeout;
  global.setTimeout = (fn, ms) => { const id = ++next; timers.set(id, { fn, ms }); return id; };
  global.clearTimeout = id => { timers.delete(id); };
  const mod = { exports: {} };
  new Function('require','module','exports',compiled.outputText)(id => {
    if (id === 'react') return react;
    if (id === 'react-native') return native;
    if (id === './apiBase') return { API_BASE: 'https://backend.test' };
    if (id === '../components/AppToast') return { toast: { warn() {}, info() {} } };
    throw new Error('Optional integration not installed');
  },mod,mod.exports);
  mod.exports.useNetworkStatus();
  const cleanup = effects.map(fn => fn());
  return {
    state, timers,
    fire(ms) {
      const row = [...timers].find(([, item]) => item.ms === ms);
      assert.ok(row, 'missing timer '+ms);
      timers.delete(row[0]); row[1].fn();
    },
    notify(value) { listener?.(value); },
    dispose() { for (const fn of cleanup) fn?.(); global.setTimeout = oldTimeout; global.clearTimeout = oldClear; },
  };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
test('reachability probe cannot run beyond its transport deadline', async () => {
  const original = global.fetch;
  const f = hookFixture();
  global.fetch = () => new Promise(() => {});
  try {
    f.fire(0);
    await settle();
    f.fire(4000);
    await settle();
    assert.equal(f.state[0].online, false);
    assert.ok([...f.timers.values()].some(t => t.ms === 15000));
  } finally { global.fetch = original; f.dispose(); }
});
test('background aborts pending probes without marking the app offline', async () => {
  const original = global.fetch;
  let finish;
  const f = hookFixture();
  global.fetch = () => new Promise(resolve => { finish = resolve; });
  try {
    f.fire(0); await settle();
    f.notify('background');
    finish({ ok: false });
    await settle();
    assert.equal(f.state[0].online, true);
    assert.equal(f.timers.size, 0);
  } finally { global.fetch = original; f.dispose(); }
});
test('foreground restoration re-arms exactly one probe', () => {
  const f = hookFixture();
  try {
    f.notify('background');
    for (let i=0;i<20;i++) f.notify('active');
    assert.equal(f.timers.size, 1);
  } finally { f.dispose(); }
});
