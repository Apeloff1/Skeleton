'use strict';
// Execute the actual page and retained-store owner with React/platform and
// HTTP seams isolated. No generation, provider, installed API or build runs.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
const JOB = 'original-playable-job';
const KEY = 'engine-chat:original-request';
const GAME = 'owned-playable-game';
const game = (changes = {}) => ({ playable_id: GAME, title: 'Owned original game', genre: 'puzzle',
  status: 'ready', playability_score: 90, version: 1, raw_path: '/api/playable/' + GAME + '/raw', ...changes });
const repairRetained = (changes = {}) => ({ jobId: JOB, kind: 'repair', playableId: GAME, engineRequestKey: KEY,
  errorCode: 'project_model_execution_unconfirmed', ...changes });
const retained = () => ({ jobId: JOB, kind: 'generate', engineRequestKey: KEY, errorCode: 'project_model_execution_unconfirmed' });
const unconfirmed = () => ({ ok: true, status: 200, data: { job_id: JOB, job_status: 'unconfirmed', kind: 'generate',
  engine_request_key: KEY, error_code: 'project_model_execution_unconfirmed', retry_same_request: true } });
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function nodes(node) {
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(nodes);
  return [node, ...nodes(node.props?.children)];
}
function text(node) {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (!node || typeof node !== 'object') return '';
  if (Array.isArray(node)) return node.map(text).join(' ');
  return text(node.props?.children);
}
const find = (tree, id) => nodes(tree).find(node => node.props?.testID === id);
function fixture(disk = new Map()) {
  let epoch = 0, actor = 'actor-a', now = Date.parse('2026-10-25T09:00:00Z'), timerId = 0, active;
  const timers = new Map(), observers = new Set(), effects = [], calls = [], stateWrites = [];
  const clock = { setTimeout(fn, ms = 0, ...args) { const id = ++timerId; timers.set(id, { at: now + ms, run: () => fn(...args) }); return id; },
    clearTimeout(id) { timers.delete(id); } };
  class ClockDate extends Date { constructor(value) { super(arguments.length ? value : now); } static now() { return now; } }
  function load(file, imports = {}) {
    const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, file), 'utf8'), { fileName: file, reportDiagnostics: true,
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } });
    assert.equal(output.diagnostics.length, 0, file + ' must compile');
    const module = { exports: {} };
    compileFunction(output.outputText, ['require', 'module', 'exports', 'setTimeout', 'clearTimeout', 'Date'])(id => {
      assert.ok(Object.hasOwn(imports, id), file + ': unexpected dependency ' + id); return imports[id];
    }, module, module.exports, clock.setTimeout, clock.clearTimeout, ClockDate);
    return module.exports;
  }
  const auth = { getAuthEpoch: () => epoch, resolveStorageTenantIdentity: async () => ({ tenantId: 'tenant-a', principalId: actor }),
    subscribeAuthChanges(fn) { observers.add(fn); return () => observers.delete(fn); } };
  const storage = { getItem: async key => disk.get(key) ?? null, setItem: async (key, value) => { disk.set(key, value); },
    removeItem: async key => { disk.delete(key); } };
  const store = load('src/product/playableJobObservation.ts', {
    '@react-native-async-storage/async-storage': storage, '../auth/gameforgeAuth': auth,
    '../utils/OrderedCommitQueue': load('src/utils/OrderedCommitQueue.ts'),
  });
  const lifecycle = load('src/product/buildJobLifecycle.ts');
  const identity = load('src/product/creatorIdentity.ts', { '../auth/gameforgeAuth': auth });
  const wire = { job: async () => unconfirmed(), post: async () => ({ ok: true, status: 202, data: { job_id: JOB } }),
    get: async () => ({ ok: true, status: 200, data: { playables: [], leaderboard: [], builds: [] } }) };
  const api = { get: async (url, options = {}) => {
    calls.push({ method: 'GET', url, options });
    if (url.startsWith('/api/playable/job/')) return wire.job(url, options);
    return wire.get(url, options);
  }, post: async (url, body, options = {}) => { calls.push({ method: 'POST', url, body, options }); return wire.post(url, body, options); } };
  const scope = name => ({ name, slots: [], cursor: 0, mounted: true });
  const shell = scope('shell'); let content = scope('content:initial'), contentKey;
  function cleanup(value) { value.mounted = false; for (const slot of value.slots) if (slot?.cleanup) { slot.cleanup(); slot.cleanup = undefined; } }
  const React = {
    useState(initial) { const owner = active, i = owner.cursor++; if (!owner.slots[i]) owner.slots[i] = { value: typeof initial === 'function' ? initial() : initial };
      const slot = owner.slots[i]; return [slot.value, value => {
        stateWrites.push({ owner: owner.name, mounted: owner.mounted });
        if (owner.mounted) slot.value = typeof value === 'function' ? value(slot.value) : value;
      }]; },
    useRef(value) { const i = active.cursor++; if (!active.slots[i]) active.slots[i] = { current: value }; return active.slots[i]; },
    useCallback(fn, deps) { const i = active.cursor++, old = active.slots[i];
      if (!old || deps.some((value, j) => !Object.is(value, old.deps[j]))) active.slots[i] = { value: fn, deps }; return active.slots[i].value; },
    useEffect(run, deps) { const owner = active, i = owner.cursor++, old = owner.slots[i];
      if (!old || deps.some((value, j) => !Object.is(value, old.deps[j]))) {
        const next = { deps, cleanup: old?.cleanup }; owner.slots[i] = next;
        effects.push(() => { if (!owner.mounted) return; next.cleanup?.(); next.cleanup = run(); });
      } },
    useSyncExternalStore(subscribe, snapshot) { const i = active.cursor++; if (!active.slots[i]) active.slots[i] = { cleanup: subscribe(() => {}) }; return snapshot(); },
  };
  const element = (type, props, key) => ({ type, props: props || {}, key });
  const rn = Object.fromEntries(['View', 'Text', 'ScrollView', 'TouchableOpacity', 'ActivityIndicator', 'TextInput', 'SafeAreaView',
    'KeyboardAvoidingView', 'Switch', 'Modal'].map(name => [name, name]));
  rn.Platform = { OS: 'web' }; rn.StyleSheet = { create: value => value }; rn.Dimensions = { get: () => ({ width: 390, height: 844 }) };
  rn.Animated = { View: 'Animated.View' }; rn.Easing = {}; rn.Alert = { alert() {} };
  const haptics = { selection() {}, notify() {} }, params = {};
  const Page = load('app/playable.tsx', {
    react: { __esModule: true, default: React }, 'react/jsx-runtime': { jsx: element, jsxs: element }, 'react-native': rn,
    'expo-clipboard': { setStringAsync: async () => {} }, 'expo-router': { useRouter: () => ({ back() {}, push() {} }), useLocalSearchParams: () => params },
    '../src/utils/apiBase': { API_BASE: 'https://backend.test' }, '../src/utils/apiClient': { __esModule: true, default: api },
    '../src/components/PrivateImage': { __esModule: true, default: 'PrivateImage', savePrivateImage: async () => 'saved' },
    '../src/features/Playable/GamePreview': { __esModule: true, default: 'GamePreview' }, '../src/hooks/useHaptics': { useHaptics: () => haptics },
    '../src/utils/safeStorage': { safeGetItem: async () => null, safeSetItem: async () => {} }, '../src/utils/liveops': { awardXp() {} },
    '../src/auth/gameforgeAuth': auth, '../src/product/creatorIdentity': identity, '../src/product/buildJobLifecycle': lifecycle,
    '../src/product/playableJobObservation': store, '../src/theme/tokens': { __esModule: true, default: { hitSlop: { md: {} } } },
  }).default;
  const f = { calls, disk, wire, stateWrites, params,
    render() {
      active = shell; shell.cursor = 0; const child = Page();
      if (contentKey !== child.key) { cleanup(content); content = scope('content:' + child.key); contentKey = child.key; }
      active = content; content.cursor = 0; return child.type(child.props);
    },
    effects() { while (effects.length) effects.shift()(); },
    async flush() {
      let tree;
      for (let i = 0; i < 20; i++) { const writes = stateWrites.length; tree = f.render(); f.effects(); await tick();
        if (writes === stateWrites.length && effects.length === 0) return tree;
      }
      throw new Error('Page fixture did not settle');
    },
    async advance(milliseconds) {
      now += milliseconds;
      for (const [id, timer] of [...timers].sort((a, b) => a[1].at - b[1].at)) if (timer.at <= now && timers.has(id)) { timers.delete(id); timer.run(); }
      return f.flush();
    },
    async saved() { const current = await store.openPlayableJobObservation(); try { return await current.get(); } finally { current.dispose(); } },
    async seed(value = retained()) { const current = await store.openPlayableJobObservation(); try { await current.set(value); } finally { current.dispose(); } },
    changeAccount(next = 'actor-b') { epoch++; actor = next; for (const observer of observers) observer(); },
    unmount() { cleanup(content); cleanup(shell); timers.clear(); },
  };
  return f;
}
const jobCalls = f => f.calls.filter(call => call.url.startsWith('/api/playable/job/'));
const posts = f => f.calls.filter(call => call.method === 'POST');
const repairPosts = f => posts(f).filter(call => call.url === '/api/playable/' + GAME + '/repair/async');
const gameReads = f => f.calls.filter(call => call.method === 'GET' && call.url === '/api/playable/' + GAME);
async function crashedGame(f) {
  f.params.id = GAME;
  const defaultGet = f.wire.get;
  f.wire.get = async (url, options) => url === '/api/playable/' + GAME
    ? { ok: true, status: 200, data: game() } : defaultGet(url, options);
  let tree = await f.flush();
  const preview = find(tree, 'pl-webview'); assert.ok(preview, 'An actual owned game must load before repair');
  preview.props.onGameError('Assignment to constant variable.');
  tree = await f.flush(); assert.ok(find(tree, 'pl-repair-banner'));
  return tree;
}

test('reload displays the original owner-scoped job and engine key without any automatic observation or generation', async t => {
  const first = fixture(); await first.seed(); first.unmount();
  const f = fixture(first.disk); t.after(() => f.unmount()); const tree = await f.flush();
  assert.match(text(find(tree, 'pl-job-id')), new RegExp(JOB)); assert.ok(text(tree).includes(KEY));
  assert.match(text(find(tree, 'pl-job-status')), /saved job|awaiting observation/i);
  assert.equal(find(tree, 'pl-generate').props.disabled, true);
  assert.equal(find(tree, 'pl-job-resume').props.disabled, false);
  assert.equal(jobCalls(f).length, 0); assert.equal(posts(f).length, 0); assert.deepEqual(await f.saved(), retained());
});

test('Resume GETs only the same job and retains an honest unconfirmed outcome without generating or changing request identity', async t => {
  const f = fixture(); t.after(() => f.unmount()); await f.seed(); let tree = await f.flush();
  find(tree, 'pl-job-resume').props.onPress(); tree = await f.flush();
  assert.equal(jobCalls(f).length, 1); assert.equal(jobCalls(f)[0].url, '/api/playable/job/' + JOB);
  assert.equal(jobCalls(f)[0].options.retries, 0); assert.ok(jobCalls(f)[0].options.signal instanceof AbortSignal);
  assert.equal(jobCalls(f)[0].options.idempotencyKey, undefined); assert.equal(posts(f).length, 0);
  assert.match(text(find(tree, 'pl-job-status')), /not confirmed/i);
  assert.match(text(find(tree, 'pl-job-status')), /does not restart|same job/i);
  assert.deepEqual(await f.saved(), retained()); assert.ok(text(tree).includes(KEY));
  assert.equal(find(tree, 'pl-generate').props.disabled, true);
});

test('a newly submitted unconfirmed job paints and persists its original identity before allowing another generation', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await f.flush();
  assert.equal(find(tree, 'pl-generate').props.disabled, false);
  const generating = find(tree, 'pl-generate').props.onPress(); tree = await f.flush(); await generating;
  assert.equal(posts(f).length, 1); assert.equal(posts(f)[0].url, '/api/playable/generate/async');
  assert.equal(posts(f)[0].options.retries, 0); assert.equal(jobCalls(f).length, 1);
  assert.match(text(find(tree, 'pl-job-id')), new RegExp(JOB)); assert.match(text(find(tree, 'pl-job-status')), /not confirmed/i);
  const saved = await f.saved(); assert.equal(saved.jobId, JOB); assert.equal(saved.engineRequestKey, KEY);
  assert.equal(find(tree, 'pl-generate').props.disabled, true);
});

test('explicit dismissal forgets only the observation and sends no backend cancellation or generation', async t => {
  const f = fixture(); t.after(() => f.unmount()); await f.seed(); let tree = await f.flush();
  assert.match(text(tree), /does not cancel the backend job/i);
  find(tree, 'pl-job-dismiss').props.onPress(); tree = await f.flush();
  assert.equal(await f.saved(), null); assert.equal(find(tree, 'pl-job-id'), undefined);
  assert.equal(find(tree, 'pl-generate').props.disabled, false); assert.equal(posts(f).length, 0); assert.equal(jobCalls(f).length, 0);
});

test('only an observed terminal job clears the retained identity and releases the generation control', async t => {
  const f = fixture(); t.after(() => f.unmount()); await f.seed(); let tree = await f.flush();
  f.wire.job = async () => ({ ok: true, data: { job_id: JOB, job_status: 'error', error: 'Confirmed backend generation failure' } });
  find(tree, 'pl-job-resume').props.onPress(); tree = await f.flush();
  assert.equal(await f.saved(), null); assert.equal(find(tree, 'pl-job-id'), undefined);
  assert.match(text(find(tree, 'pl-error')), /Confirmed backend generation failure/);
  assert.equal(find(tree, 'pl-generate').props.disabled, false); assert.equal(posts(f).length, 0);
});

test('the finite observation limit retains the reference and never misreports backend failure', async t => {
  const f = fixture(); t.after(() => f.unmount()); await f.seed(); let tree = await f.flush();
  f.wire.job = async () => ({ ok: true, data: { job_id: JOB, job_status: 'running' } });
  find(tree, 'pl-job-resume').props.onPress(); await f.flush();
  for (let i = 0; i < 61 && jobCalls(f).length < 60; i++) tree = await f.advance(15000);
  tree = await f.flush();
  assert.equal(jobCalls(f).length, 60); assert.equal(posts(f).length, 0); assert.deepEqual(await f.saved(), retained());
  assert.match(text(find(tree, 'pl-job-status')), /Observation timed out.*may still be running/i);
  assert.equal(find(tree, 'pl-generate').props.disabled, true);
});

test('account changes fence in-flight native reads and stale Resume closures before another owner can see them', async t => {
  const f = fixture(); t.after(() => f.unmount()); await f.seed(); let tree = await f.flush();
  const pending = deferred(); f.wire.job = () => pending.promise;
  const staleResume = find(tree, 'pl-job-resume').props.onPress; staleResume(); await f.flush();
  const request = jobCalls(f)[0]; f.changeAccount(); tree = await f.flush();
  assert.equal(request.options.signal.aborted, true); assert.equal(find(tree, 'pl-job-id'), undefined);
  const count = jobCalls(f).length; staleResume(); await f.flush(); assert.equal(jobCalls(f).length, count);
  pending.resolve({ ok: true, data: { job_id: JOB, job_status: 'error', error: 'Old owner secret failure' } });
  tree = await f.flush(); assert.equal(text(tree).includes('Old owner secret failure'), false);
  assert.equal(await f.saved(), null); assert.equal(posts(f).length, 0);
  f.changeAccount('actor-a'); tree = await f.flush();
  assert.match(text(find(tree, 'pl-job-id')), new RegExp(JOB)); assert.deepEqual(await f.saved(), retained());
  assert.equal(jobCalls(f).length, count, 'Returning to the owner restores its receipt without automatic monitoring');
});

test('runtime repair accepts only one POST before acknowledgement and retains the same uncertain repair job', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await crashedGame(f);
  const pending = deferred();
  f.wire.post = async url => url.endsWith('/repair/async') ? pending.promise : { ok: true, data: {} };
  f.wire.job = async () => ({ ok: true, data: { ...unconfirmed().data, kind: 'repair', parent_id: GAME } });
  const repair = find(tree, 'pl-repair-btn').props.onPress;
  const started = repair(); repair(); tree = await f.flush();
  assert.equal(repairPosts(f).length, 1, 'A rapid or stale callback must not submit another repair');
  assert.equal(repairPosts(f)[0].options.retries, 0);
  assert.deepEqual(repairPosts(f)[0].body, { error: 'Assignment to constant variable.' });
  pending.resolve({ ok: true, status: 202, data: { job_id: JOB, job_status: 'running' } });
  tree = await f.flush(); await started; tree = await f.flush();
  assert.deepEqual(await f.saved(), repairRetained());
  assert.match(text(find(tree, 'pl-job-status')), /not confirmed/i);
  assert.equal(find(tree, 'pl-repair-btn').props.disabled, true);
  assert.equal(find(tree, 'pl-generate').props.disabled, true);
  repair(); await f.flush(); assert.equal(repairPosts(f).length, 1, 'A stale pre-repair handler cannot bypass retained custody');
  assert.ok(jobCalls(f).every(call => call.url === '/api/playable/job/' + JOB && call.options.retries === 0));
});

test('a confirmed matching runtime repair reloads only its owned game and clears the actual crash', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await crashedGame(f);
  const previousPreview = find(tree, 'pl-webview'); const readsBefore = gameReads(f).length;
  f.wire.job = async () => ({ ok: true, data: { job_id: JOB, job_status: 'done', kind: 'repair',
    playable_id: GAME, repaired: true, score: 95 } });
  f.wire.get = async url => ({ ok: true, status: 200, data: url === '/api/playable/' + GAME
    ? game({ title: 'Corrected owned game', version: 2, playability_score: 95 }) : { playables: [] } });
  await find(tree, 'pl-repair-btn').props.onPress(); tree = await f.flush();
  assert.equal(repairPosts(f).length, 1); assert.equal(gameReads(f).length, readsBefore + 1);
  assert.equal(await f.saved(), null); assert.equal(find(tree, 'pl-repair-banner'), undefined);
  assert.match(text(tree), /Corrected owned game/);
  const preview = find(tree, 'pl-webview'); assert.ok(preview); assert.notEqual(preview.key, previousPreview.key);
  assert.equal(preview.props.uri, 'https://backend.test/api/playable/' + GAME + '/raw');
  assert.equal(posts(f).filter(call => !call.url.endsWith('/play') && !call.url.endsWith('/repair/async')).length, 0,
    'Observing the repair must not create covers, another build, or another repair');
});

test('a confirmed unsuccessful repair preserves the original preview and crash instead of reporting fixed', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await crashedGame(f);
  const previousPreview = find(tree, 'pl-webview'); const readsBefore = gameReads(f).length;
  f.wire.job = async () => ({ ok: true, data: { job_id: JOB, job_status: 'done', kind: 'repair',
    playable_id: GAME, repaired: false, score: 10, error: 'The replacement was incomplete.' } });
  await find(tree, 'pl-repair-btn').props.onPress(); tree = await f.flush();
  assert.equal(await f.saved(), null); assert.equal(gameReads(f).length, readsBefore);
  assert.equal(find(tree, 'pl-webview').key, previousPreview.key);
  assert.match(text(find(tree, 'pl-repair-banner')), /Assignment to constant variable/);
  assert.doesNotMatch(text(find(tree, 'pl-repair-banner')), /✓ Fixed/);
  assert.equal(repairPosts(f).length, 1);
});

test('a foreign terminal repair identity cannot clear retained work or replace the displayed source', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await crashedGame(f);
  const previousPreview = find(tree, 'pl-webview'); const readsBefore = gameReads(f).length;
  f.wire.job = async () => ({ ok: true, data: { job_id: JOB, job_status: 'done', kind: 'repair',
    playable_id: 'different-owner-game', repaired: true, score: 100 } });
  const running = find(tree, 'pl-repair-btn').props.onPress(); await f.flush();
  for (let i = 0; i < 3 && jobCalls(f).length < 3; i++) await f.advance(15000);
  await running; tree = await f.flush();
  const saved = await f.saved(); assert.equal(saved.jobId, JOB); assert.equal(saved.kind, 'repair'); assert.equal(saved.playableId, GAME);
  assert.equal(gameReads(f).length, readsBefore); assert.equal(find(tree, 'pl-webview').key, previousPreview.key);
  assert.match(text(find(tree, 'pl-repair-banner')), /Assignment to constant variable/);
  assert.equal(find(tree, 'pl-repair-btn').props.disabled, true); assert.equal(repairPosts(f).length, 1);
  assert.ok(!f.calls.some(call => call.url === '/api/playable/different-owner-game'));
});

test('repair observation timeout retains its exact parent and blocks repeat repair submissions', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await crashedGame(f);
  f.wire.job = async () => ({ ok: true, data: { job_id: JOB, job_status: 'running', kind: 'repair', parent_id: GAME } });
  const staleRepair = find(tree, 'pl-repair-btn').props.onPress; const running = staleRepair(); await f.flush();
  for (let i = 0; i < 61 && jobCalls(f).length < 60; i++) tree = await f.advance(15000);
  await running; tree = await f.flush();
  assert.equal(jobCalls(f).length, 60); assert.equal(repairPosts(f).length, 1);
  const saved = await f.saved(); assert.equal(saved.jobId, JOB); assert.equal(saved.kind, 'repair'); assert.equal(saved.playableId, GAME);
  assert.match(text(find(tree, 'pl-job-status')), /Observation timed out.*may still be running/i);
  assert.equal(find(tree, 'pl-repair-btn').props.disabled, true);
  staleRepair(); await f.flush(); assert.equal(repairPosts(f).length, 1);
});

test('a retained repair resumes after reload with only original GETs and no new generation or cover', async t => {
  const f = fixture(); t.after(() => f.unmount()); await f.seed(repairRetained());
  f.wire.job = async () => ({ ok: true, data: { job_id: JOB, job_status: 'done', kind: 'repair',
    playable_id: GAME, repaired: true, score: 95 } });
  f.wire.get = async url => ({ ok: true, status: 200, data: url === '/api/playable/' + GAME
    ? game({ title: 'Recovered corrected game', version: 2 }) : { playables: [] } });
  let tree = await f.flush(); assert.equal(jobCalls(f).length, 0); assert.equal(posts(f).length, 0);
  find(tree, 'pl-job-resume').props.onPress(); tree = await f.flush();
  assert.equal(jobCalls(f).length, 1); assert.equal(jobCalls(f)[0].url, '/api/playable/job/' + JOB);
  assert.equal(gameReads(f).length, 1); assert.equal(posts(f).length, 0); assert.equal(await f.saved(), null);
  assert.ok(find(tree, 'pl-webview')); assert.match(text(tree), /Recovered corrected game/);
});

test('an account change fences a late repair acknowledgement and stale repair callback', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await crashedGame(f);
  const pending = deferred(); f.wire.post = async url => url.endsWith('/repair/async') ? pending.promise : { ok: true, data: {} };
  const repair = find(tree, 'pl-repair-btn').props.onPress; const running = repair(); await f.flush();
  assert.equal(repairPosts(f).length, 1); f.changeAccount(); tree = await f.flush();
  pending.resolve({ ok: true, status: 202, data: { job_id: JOB, job_status: 'running' } });
  await running; tree = await f.flush();
  assert.equal(await f.saved(), null); assert.equal(find(tree, 'pl-job-id'), undefined);
  assert.equal(jobCalls(f).length, 0); assert.equal(text(tree).includes(JOB), false);
  repair(); await f.flush(); assert.equal(repairPosts(f).length, 1);
});

test('a repaired acknowledgement with unreadable metadata keeps the repair reference and original crash', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await crashedGame(f);
  const previousPreview = find(tree, 'pl-webview');
  f.wire.job = async () => ({ ok: true, data: { job_id: JOB, job_status: 'done', kind: 'repair',
    playable_id: GAME, repaired: true, score: 95 } });
  f.wire.get = async url => url === '/api/playable/' + GAME ? { ok: false, status: 503 }
    : { ok: true, status: 200, data: { playables: [] } };
  await find(tree, 'pl-repair-btn').props.onPress(); tree = await f.flush();
  const saved = await f.saved(); assert.equal(saved.jobId, JOB); assert.equal(saved.playableId, GAME);
  assert.equal(find(tree, 'pl-webview').key, previousPreview.key);
  assert.match(text(find(tree, 'pl-repair-banner')), /Assignment to constant variable/);
  assert.equal(find(tree, 'pl-repair-btn').props.disabled, true); assert.equal(repairPosts(f).length, 1);
});

test('an uncertain repair response for another parent cannot replace the original engine request reference', async t => {
  const f = fixture(); t.after(() => f.unmount()); let tree = await crashedGame(f);
  f.wire.job = async () => ({ ok: true, data: { ...unconfirmed().data, kind: 'repair',
    parent_id: 'different-owner-game', engine_request_key: 'engine-chat:foreign-parent-request' } });
  const running = find(tree, 'pl-repair-btn').props.onPress(); await f.flush();
  for (let i = 0; i < 3 && jobCalls(f).length < 3; i++) await f.advance(15000);
  await running; tree = await f.flush();
  const saved = await f.saved(); assert.equal(saved.jobId, JOB); assert.equal(saved.playableId, GAME);
  assert.equal(saved.engineRequestKey, undefined); assert.equal(saved.errorCode, undefined);
  assert.equal(text(tree).includes('engine-chat:foreign-parent-request'), false);
  assert.ok(find(tree, 'pl-repair-banner')); assert.equal(find(tree, 'pl-repair-btn').props.disabled, true);
  assert.equal(repairPosts(f).length, 1);
});
