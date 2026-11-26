'use strict';
// The gateway client only talks to /api/forge-gateway and never sends an engine seal.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

const ROOT = path.resolve(__dirname, '..', '..');
function load(relative, imports) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, relative), 'utf8'), {
    fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  assert.equal(output.diagnostics.length, 0);
  const module = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])((id) => {
    assert.ok(Object.hasOwn(imports, id), `${relative}: unexpected dependency ${id}`);
    return imports[id];
  }, module, module.exports);
  return module.exports;
}

const calls = [];
const fakeApi = {
  post: async (url, body, opts) => { calls.push({ method: 'POST', url, body, opts }); return { ok: true, status: 202, data: { execution_id: 'job_1', status: 'queued', status_ref: '/api/forge-gateway/game/build/job_1' }, error: null, rid: 'r' }; },
  get: async (url, opts) => { calls.push({ method: 'GET', url, opts }); return { ok: true, status: 200, data: { execution_id: 'job_1', status: 'running' }, error: null, rid: 'r' }; },
};
const client = load('src/forgeGateway/client.ts', { '../utils/apiClient': { __esModule: true, default: fakeApi } });

test('startGameBuild posts a trimmed brief with an idempotency key and no seal', async () => {
  const res = await client.startGameBuild({ brief: '  A small platformer  ', playtest: 'require', idempotencyKey: 'ng-test-0001' });
  assert.equal(res.data.execution_id, 'job_1');
  const call = calls.at(-1);
  assert.equal(call.url, '/api/forge-gateway/game/build');
  assert.deepEqual(call.body, { brief: 'A small platformer', playtest: 'require' });
  assert.equal(call.opts.idempotencyKey, 'ng-test-0001');
  assert.equal(call.opts.serverDedupeVerified, true, 'engine dedupes keyed builds, so a retried POST is safe');
  assert.equal(call.opts.headers, undefined, 'no custom headers, so no seal can leak');
});

test('getGameBuild encodes ids and refuses malformed ids without a request', async () => {
  const before = calls.length;
  for (const bad of ['../admin', '', 'a/b', 'x'.repeat(200)]) {
    const res = await client.getGameBuild(bad);
    assert.equal(res.ok, false);
    assert.equal(res.status, 404);
  }
  assert.equal(calls.length, before);
  await client.getGameBuild('job_1');
  assert.equal(calls.at(-1).url, '/api/forge-gateway/game/build/job_1');
});

test('no engine seal header name appears anywhere in the client source', () => {
  const src = fs.readFileSync(path.join(ROOT, 'src/forgeGateway/client.ts'), 'utf8');
  assert.doesNotMatch(src.replace(/^\s*\*.*$/gm, '').replace(/\/\/.*$/gm, ''), /x-gf-seal/i);
});
