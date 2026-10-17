'use strict';
const { compileFunction } = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
function loadTS(filename, mocks) {
  const output = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', filename), 'utf8'), {
    fileName: filename, compilerOptions: { module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020, esModuleInterop: true }, reportDiagnostics: true,
  });
  assert.equal(output.diagnostics.length, 0, filename);
  const mod = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(mocks, id), 'missing mock ' + id);
    return mocks[id];
  }, mod, mod.exports);
  return mod.exports;
}
function hooks() {
  const effects = [];
  const states = [];
  const refs = [];
  const react = {
    useState(init) {
      const index = states.length;
      states.push(typeof init === 'function' ? init() : init);
      return [states[index], update => {
        states[index] = typeof update === 'function' ? update(states[index]) : update;
      }];
    },
    useRef(value) { const ref = { current: value }; refs.push(ref); return ref; },
    useEffect(callback) { effects.push(callback); },
  };
  let cleanups = [];
  return {
    react, states, refs,
    mount() { cleanups = effects.map(fn => fn()).filter(fn => typeof fn === 'function'); },
    unmount() { for (const fn of cleanups.reverse()) fn(); cleanups = []; },
  };
}
function fixture({ load, save } = {}) {
  const h = hooks();
  const saved = new Map();
  const writes = [];
  const persist = loadTS('utils/usePersistentState.ts', {
    react: h.react,
    './safeStorage': {
      safeGetItem: load || (async key => saved.get(key) ?? null),
      safeSetItem: save || (async (key, value) => {
        writes.push({ key, value }); saved.set(key, value); return true;
      }),
    },
    './safeJson': { safeJsonParse: (raw, fallback) => {
      try { return JSON.parse(raw); } catch { return fallback; }
    } },
  });
  return { h, persist, saved, writes };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const pause = () => new Promise(resolve => setTimeout(resolve, 8));

test('late hydration must not overwrite an edit made by the user', async () => {
  let resolveLoad;
  const f = fixture({
    load: () => new Promise(resolve => { resolveLoad = resolve; }),
  });
  const [, set] = f.persist.usePersistentState('theme', 'light', { debounceMs: 0 });
  f.h.mount();
  set('dark');
  resolveLoad('"light"');
  await tick(); await pause();
  assert.equal(f.h.states[0], 'dark');
  assert.equal(f.writes[0].value, '"dark"');
  f.h.unmount();
});

test('unedited state restores a persisted value after native hydration', async () => {
  const f = fixture({ load: async () => '{"open":true}' });
  f.persist.usePersistentState('menu', { open: false });
  f.h.mount();
  await tick();
  assert.deepEqual(f.h.states[0], { open: true });
  assert.equal(f.writes.length, 0);
  f.h.unmount();
});

test('multiple functional updates compose on the latest local snapshot', async () => {
  const f = fixture();
  const [, set] = f.persist.usePersistentState('counter', 0, { debounceMs: 0 });
  f.h.mount();
  await tick();
  set(n => n + 1);
  set(n => n + 1);
  set(n => n + 1);
  await pause();
  assert.equal(f.h.states[0], 3);
  assert.equal(f.writes.at(-1).value, '3');
  f.h.unmount();
});

test('unmount flushes a delayed preference write', async () => {
  const f = fixture();
  const [, set] = f.persist.usePersistentState('draft-layout', 'A', { debounceMs: 60_000 });
  f.h.mount();
  await tick();
  set('B');
  f.h.unmount();
  await tick();
  assert.equal(f.saved.get('@persist/1/draft-layout'), '"B"');
});

test('old native save cannot overtake a newer queued write', async () => {
  let releaseFirst;
  const completed = [];
  let started = 0;
  const f = fixture({
    save: (_key, value) => {
      started++;
      if (started === 1) {
        return new Promise(resolve => { releaseFirst = () => {
          completed.push(value); resolve(true);
        }; });
      }
      completed.push(value);
      return Promise.resolve(true);
    },
  });
  const a = f.persist.queuePersistentStateWrite('@persist/1/key', '"old"');
  await tick();
  const b = f.persist.queuePersistentStateWrite('@persist/1/key', '"new"');
  await tick();
  assert.equal(started, 1);
  releaseFirst();
  assert.equal(await a, true);
  assert.equal(await b, true);
  assert.deepEqual(completed, ['"old"', '"new"']);
  assert.equal(f.persist.pendingPersistentStateKeys(), 0);
});

test('native write failure cannot poison subsequent preference saves', async () => {
  let attempts = 0;
  const f = fixture({ save: async () => ++attempts > 1 });
  assert.equal(await f.persist.queuePersistentStateWrite('@persist/1/key', '1'), false);
  assert.equal(await f.persist.queuePersistentStateWrite('@persist/1/key', '2'), true);
  assert.equal(f.persist.pendingPersistentStateKeys(), 0);
});

test('large and invalid payloads are refused instead of silently overwriting state', async () => {
  const f = fixture();
  assert.equal(await f.persist.queuePersistentStateWrite('@persist/1/key', 'x'.repeat(1024 * 1024 + 1)), false);
  assert.equal(await f.persist.queuePersistentStateWrite('@boot/trace', 'bad'), false);
  const [, set] = f.persist.usePersistentState('huge', 'initial', { debounceMs: 0 });
  f.h.mount();
  await tick();
  set('x'.repeat(1024 * 1024 + 1));
  await pause();
  assert.equal(f.writes.length, 0);
  f.h.unmount();
});

test('unmount before hydration invalidates late React updates', async () => {
  let release;
  const f = fixture({ load: () => new Promise(resolve => { release = resolve; }) });
  f.persist.usePersistentState('tab', 'initial');
  f.h.mount();
  f.h.unmount();
  release('"late"');
  await tick();
  assert.equal(f.h.states[0], 'initial');
});

test('version keys isolate incompatible state schemas', async () => {
  const f = fixture();
  await f.persist.queuePersistentStateWrite('@persist/1/layout', '"v1"');
  await f.persist.queuePersistentStateWrite('@persist/2/layout', '"v2"');
  assert.equal(f.saved.get('@persist/1/layout'), '"v1"');
  assert.equal(f.saved.get('@persist/2/layout'), '"v2"');
});

test('serialized native saves drain their key occupancy after many writes', async () => {
  const f = fixture();
  const jobs = [];
  for (let i=0;i<250;i++) {
    jobs.push(f.persist.queuePersistentStateWrite('@persist/1/sweep', String(i)));
  }
  assert.equal(f.persist.pendingPersistentStateKeys(), 1);
  assert.ok((await Promise.all(jobs)).every(Boolean));
  await tick();
  assert.equal(f.persist.pendingPersistentStateKeys(), 0);
  assert.equal(f.saved.get('@persist/1/sweep'), '249');
});
