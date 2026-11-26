const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function harness() {
  let epoch = 1;
  const calls = [];
  const transfers = [];
  let handler = async () => ({ ok: true, status: 200, data: {} });
  const api = Object.fromEntries(['get', 'post'].map(method => [method, (url, ...args) => {
    calls.push({ method, url, args }); return handler(method, url, ...args);
  }]));
  const mod = { exports: {} };
  const source = fs.readFileSync(path.join(__dirname, '../../src/skeletonForge/durableForgeClient.ts'), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(output, { module: mod, exports: mod.exports, Uint8Array, AbortController,
    require(name) {
      if (name.endsWith('/apiClient')) return { __esModule: true, default: api };
      if (name.endsWith('/gameforgeAuth')) return { getAuthEpoch: () => epoch };
      if (name.endsWith('/gameLearningClient')) return {
        learningRequestKey: () => 'source-key',
        downloadConsoleArtifact: async (...args) => { transfers.push(args); return new Uint8Array([80, 75]); },
      };
      throw new Error('Unexpected dependency: ' + name);
    },
  });
  return { client: mod.exports, calls, transfers, setHandler: fn => { handler = fn; }, changeAccount: () => { epoch++; } };
}
function request() {
  return { vision: 'A racing game with three checkpoints.', target: 'godot', archetype: 'pipeline',
    answers: { mood: 'bright' }, operator_axes: { tempo: 0.8 }, playable_content: true,
    playable_archetype: 'racing', playable_main_scene: true, playtest: 'require' };
}
function project() { return { project_id: 'p_one', name: 'Race', console_id: 'forge:godot', version: 2 }; }
function job() {
  return { job_id: 'j_one', project_id: 'p_one', kind: 'forge_source', status: 'completed',
    request_id: 'request-one', request_digest: 'a'.repeat(64), project_version: 2,
    brief: { ...request(), playtest: 'off', include_files: true },
    result: { state: 'source_ready', build: { succeeded: true }, artifacts: [{ artifact_id: 'a_one',
      name: 'source.zip', bytes: 100, digest: 'b'.repeat(64), format: 'zip',
      download_path: '/game-learning/projects/p_one/build-artifacts/a_one' }] } };
}
const plain = value => JSON.parse(JSON.stringify(value));

test('source scope requires an explicit choice and preserves the exact supported authored data', () => {
  const { client } = harness(); const original = request();
  assert.throws(() => client.sourceOnlyForgeRequest(original, false), /scope/);
  const saved = client.sourceOnlyForgeRequest(original, true);
  assert.equal(saved.playtest, 'off'); assert.equal(saved.include_files, true);
  assert.equal(original.playtest, 'require');
  assert.deepEqual(plain(saved.answers), original.answers);
  assert.deepEqual(plain(saved.operator_axes), original.operator_axes);
  saved.answers.mood = 'changed'; assert.equal(original.answers.mood, 'bright');
});

test('source preparation refuses non-Godot output, injected server authority, empty and oversized visions', () => {
  const { client } = harness();
  for (const change of [{ target: 'json' }, { project_root: '/private/project' }, { overwrite: true },
    { provider: 'remote' }, { vision: '' }, { vision: 'x'.repeat(4001) }, { operator_axes: { tempo: Infinity } }]) {
    assert.throws(() => client.sourceOnlyForgeRequest({ ...request(), ...change }, true));
  }
});

test('source preparation bounds nesting and rejects prototype-shaped authoring data', () => {
  const { client } = harness(); let value = {};
  for (let i = 0; i < 20; i++) value = { layer: value };
  assert.throws(() => client.sourceOnlyForgeRequest({ ...request(), galaxy_profile: value }, true));
  const poisoned = JSON.parse('{"__proto__":{"secret":true}}');
  assert.throws(() => client.sourceOnlyForgeRequest({ ...request(), answers: poisoned }, true));
});

test('project admission accepts only source-project identities with valid versions', () => {
  const { client } = harness(); assert.equal(client.checkedForgeProject(project()).project_id, 'p_one');
  for (const change of [{ project_id: '../other' }, { console_id: 'nes' }, { version: 0 }, { version: true }, { tree_digest: 'bad' }]) {
    assert.throws(() => client.checkedForgeProject({ ...project(), ...change }));
  }
});

test('job validation rejects foreign ownership, unknown states and unbound source receipts', () => {
  const { client } = harness(); assert.equal(client.checkedForgeJob(job(), 'p_one').job_id, 'j_one');
  for (const change of [{ project_id: 'p_other' }, { kind: 'console_build' }, { status: 'succeeded' },
    { request_digest: 'bad' }, { project_version: false }, { brief: { ...request(), playtest: 'require' } }]) {
    assert.throws(() => client.checkedForgeJob({ ...job(), ...change }, 'p_one'));
  }
});

test('completed jobs require successful source results and an exact bounded artifact route', () => {
  const { client } = harness();
  for (const change of [{ bytes: 0 }, { bytes: 16 * 1024 * 1024 + 1 }, { digest: 'bad' },
    { format: 'exe' }, { download_path: '/game-learning/projects/p_other/build-artifacts/a_one' }]) {
    const value = job(); Object.assign(value.result.artifacts[0], change);
    assert.throws(() => client.checkedForgeJob(value, 'p_one'));
  }
  const failed = job(); failed.result.build.succeeded = false;
  assert.throws(() => client.checkedForgeJob(failed, 'p_one'));
});

test('job states distinguish exact terminal receipts from active work', () => {
  const { client } = harness();
  for (const status of ['completed', 'interrupted', 'cancelled', 'failed']) assert.equal(client.forgeJobTerminal({ status }), true);
  for (const status of ['queued', 'running']) assert.equal(client.forgeJobTerminal({ status }), false);
});

test('read-only project and history requests never submit a compiler request', async () => {
  const h = harness(); h.setHandler(async (_method, url) => ({ ok: true, status: 200,
    data: url.endsWith('/p_one') ? { project: project(), builds: [job()], next_cursor: null } : { projects: [project()] } }));
  assert.equal((await h.client.listForgeProjects()).length, 1);
  assert.equal((await h.client.getForgeProject('p_one')).builds.length, 1);
  assert.ok(h.calls.every(call => call.method === 'get' && call.args[0].retries === 0));
});

test('a build submission binds the current project version, exact choices and original request ID once', async () => {
  const h = harness(); const reply = job(); reply.request_id = 'original-key';
  h.setHandler(async () => ({ ok: true, status: 202, data: { job: reply } }));
  const run = h.client.sourceOnlyForgeRequest(request(), true);
  await h.client.submitForgeBuild(project(), run, 'original-key');
  assert.equal(h.calls.length, 1); const call = h.calls[0];
  assert.equal(call.url, '/api/skeleton/projects/p_one/builds');
  assert.equal(call.args[0].idempotency_key, 'original-key'); assert.equal(call.args[0].expected_version, 2);
  assert.deepEqual(plain(call.args[0].run), plain(run)); assert.equal(call.args[1].retries, 0);
});

test('a different submission identity is refused instead of accepting another build', async () => {
  const h = harness(); h.setHandler(async () => ({ ok: true, status: 202, data: { job: job() } }));
  await assert.rejects(h.client.submitForgeBuild(project(), h.client.sourceOnlyForgeRequest(request(), true), 'different-key'), /request identity/);
});

test('late authenticated responses are fenced when the account changes', async () => {
  const h = harness(); let finish;
  h.setHandler(() => new Promise(resolve => { finish = resolve; }));
  const result = h.client.listForgeProjects(); h.changeAccount();
  finish({ ok: true, status: 200, data: { projects: [project()] } });
  await assert.rejects(result, /account changed/);
});

test('definitive admission errors retain HTTP status without exposing arbitrary response objects', async () => {
  const h = harness(); h.setHandler(async () => ({ ok: false, status: 409, data: { detail: { code: 'stale', message: 'Refresh this saved project.' } } }));
  await assert.rejects(h.client.getForgeProject('p_one'), error => error.status === 409 && error.message === 'Refresh this saved project.');
});

test('only explicit cancellation or prepared publication resume sends a control command', async () => {
  const h = harness(); const reply = job(); reply.status = 'interrupted'; reply.result = null;
  h.setHandler(async () => ({ ok: true, status: 200, data: { job: reply } }));
  await h.client.controlForgeBuild('p_one', 'j_one', 'resume');
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].url, '/api/skeleton/projects/p_one/builds/j_one/resume');
  assert.deepEqual(plain(h.calls[0].args[0]), {}); assert.equal(h.calls[0].args[1].retries, 0);
});

test('original ZIP download delegates exact digest-bound bytes without compilation', async () => {
  const h = harness(); const bytes = await h.client.downloadForgeBuild(job());
  assert.equal(bytes[0], 80); assert.equal(h.calls.length, 0); assert.equal(h.transfers.length, 1);
  assert.equal(h.transfers[0][0], 'p_one'); assert.equal(h.transfers[0][1].digest, 'b'.repeat(64));
  const running = job(); running.status = 'running'; running.result = null;
  await assert.rejects(h.client.downloadForgeBuild(running), /complete/);
});

test('older history uses a bounded advancing cursor and rejects repeats or mixed project records', async () => {
  const h = harness(); const older = job(); older.job_id = 'j_older';
  h.setHandler(async () => ({ ok: true, status: 200, data: { builds: [older], next_cursor: null } }));
  const page = await h.client.listForgeBuilds('p_one', 'j_one'); assert.equal(page.builds[0].job_id, 'j_older');
  assert.equal(h.calls[0].url, '/api/skeleton/projects/p_one/builds?before=j_one&limit=24');
  h.setHandler(async () => ({ ok: true, status: 200, data: { builds: [older], next_cursor: 'j_one' } }));
  await assert.rejects(h.client.listForgeBuilds('p_one', 'j_one'), /advance/);
  h.setHandler(async () => ({ ok: true, status: 200, data: { builds: Array(25).fill(older), next_cursor: null } }));
  await assert.rejects(h.client.listForgeBuilds('p_one', 'j_one'), /page is invalid/);
});
