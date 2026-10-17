'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const read = filename => fs.readFileSync(path.join(root, filename), 'utf8');
function moduleTS(filename, mocks = {}) {
  const compilation = ts.transpileModule(read(filename), {
    fileName: filename,
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
    reportDiagnostics: true,
  });
  assert.equal((compilation.diagnostics || []).length, 0, filename + ' transpile diagnostics');
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', compilation.outputText)(
    name => {
      assert.ok(Object.prototype.hasOwnProperty.call(mocks, name), 'unexpected import: ' + name);
      return mocks[name];
    }, mod, mod.exports,
  );
  return mod.exports;
}
const stage = (id, deps = [], phase = 0, critical = false, run = async () => ({ ok: true })) =>
  ({ id, label: id, deps, phase, critical, weight: 1, timeoutMs: 50, retries: 0, run });
const runnerModule = () => moduleTS('src/boot/runner.ts', {
  '../utils/breadcrumbs': { trail: { add() {} } },
});

test('boot graph validates legitimate local, network and maintenance phases', () => {
  const { validateBootStages } = runnerModule();
  assert.doesNotThrow(() => validateBootStages([
    stage('storage', [], 0, true),
    stage('runtime', ['storage'], 1),
    stage('prune', ['storage'], 2),
  ]));
});

test('boot graph fails closed on missing dependencies and phase inversions', () => {
  const { validateBootStages } = runnerModule();
  assert.throws(() => validateBootStages([stage('storage', ['nonexistent'], 0, true)]), /dependency/);
  assert.throws(() => validateBootStages([
    stage('storage', ['remote'], 0, true), stage('remote', [], 1),
  ]), /dependency/);
});

test('boot graph detects cycles and duplicate IDs', () => {
  const { validateBootStages } = runnerModule();
  assert.throws(() => validateBootStages([
    stage('storage', ['network'], 0, true), stage('network', ['storage'], 0),
  ]), /cyclic/);
  assert.throws(() => validateBootStages([stage('storage'), stage('storage')]), /duplicate/);
});

test('boot contracts reject bad timeouts and unbounded retry counts', () => {
  const { validateBootStages } = runnerModule();
  assert.throws(() => validateBootStages([{ ...stage('storage'), timeoutMs: 0 }]), /contract/);
  assert.throws(() => validateBootStages([{ ...stage('storage'), retries: 1_000 }]), /retry budget/);
});

test('failed optional dependencies do not execute dependent side effects', async () => {
  const { BootRunner } = runnerModule();
  let invoked = false;
  const b = new BootRunner([
    stage('local', [], 0, true),
    stage('optional', ['local'], 1, false, async () => ({ ok: false, note: 'offline' })),
    stage('dependent', ['optional'], 1, false, async () => {
      invoked = true;
      return { ok: true };
    }),
  ]);
  const result = await b.run();
  assert.equal(invoked, false);
  assert.equal(result.stages.optional.status, 'failed');
  assert.equal(result.stages.dependent.status, 'skipped');
});

test('cancellation stays terminal without native AbortController', async () => {
  const previous = global.AbortController;
  let finish;
  try {
    global.AbortController = undefined;
    const { BootRunner } = runnerModule();
    const b = new BootRunner([
      stage('local', [], 0, true, async () => new Promise(resolve => {
        finish = () => resolve({ ok: true });
      })),
    ]);
    const task = b.run();
    await new Promise(resolve => setTimeout(resolve, 10));
    b.cancel();
    assert.equal(b.snapshot().cancelled, true);
    assert.equal(b.snapshot().stages.local.status, 'skipped');
    finish();
    const complete = await task;
    assert.equal(complete.ok, false);
    assert.equal(complete.stages.local.status, 'skipped');
    b.cancel(); // repeat cancellation is idempotent
  } finally { global.AbortController = previous; }
});

test('observer snapshots are independent of the authoritative runner', () => {
  const { BootRunner } = runnerModule();
  const b = new BootRunner([stage('local', [], 0, true)]);
  const snapshot = b.snapshot();
  snapshot.stages.local.status = 'ok';
  snapshot.stages.local.deps.push('phantom');
  assert.equal(b.snapshot().stages.local.status, 'pending');
  assert.deepEqual(b.snapshot().stages.local.deps, []);
  assert.equal(b.snapshot().ok, false);
});

test('retry never fabricates a clean boot or leaves earlier callbacks authoritative', () => {
  const launcher = read('src/components/BootLauncher.tsx');
  assert.doesNotMatch(launcher, /safeSetItem\('@boot\/crash_count',\s*'0'\)/);
  assert.match(launcher, /attemptEpochRef\.current \+= 1/);
  assert.match(launcher, /epoch !== attemptEpochRef\.current/);
  assert.match(launcher, /if \(!current\(\) \|\| finalSnapshot\.cancelled\) return/);
  assert.match(launcher, /runnerRef\.current\?\.cancel\(\)/);
});

test('local readiness does not fake successes for unavailable network services', () => {
  const source = read('src/boot/stages.ts');
  assert.doesNotMatch(source, /\{ ok: true,\s*note: 'skipped' \}/);
  assert.match(source, /pruning unavailable/);
  const ids = [...source.matchAll(/\bid:\s*'([^']+)'/g)].map(x => x[1]);
  const deps = [...source.matchAll(/deps:\s*\[([^\]]*)\]/g)]
    .flatMap(x => [...x[1].matchAll(/'([^']+)'/g)].map(y => y[1]));
  assert.ok(ids.length >= 8);
  for (const id of deps) assert.ok(ids.includes(id), 'invalid dependency ' + id);
});

test('recovery reset is bounded, non-destructive by default and truthful', () => {
  const source = read('app/safe-mode.tsx');
  assert.match(source, /safeRemoveItem\('@codedock:welcome_seen:v1', 1_000\)/);
  assert.doesNotMatch(source, /await AsyncStorage\.removeItem\('@codedock:welcome_seen:v1'\)/);
  assert.match(source, /resetBootState\(\)/);
  assert.match(source, /setRecoveryError\(/);
});

test('native network listeners are never registered after unmount', () => {
  const hook = read('src/hooks/useNetworkStatus.ts');
  assert.match(hook, /if \(cancelled\) return;/);
  assert.match(hook, /unsub\?\.\(\)/);
});

test('changed release code is TypeScript syntax-valid', () => {
  for (const filename of ['src/components/BootLauncher.tsx', 'src/boot/runner.ts',
    'src/boot/stages.ts', 'app/safe-mode.tsx', 'src/hooks/useNetworkStatus.ts']) {
    const result = ts.transpileModule(read(filename), {
      fileName: filename,
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
        jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
      reportDiagnostics: true,
    });
    assert.equal((result.diagnostics || []).length, 0, filename);
  }
});
