'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');

const ROOT = path.resolve(__dirname, '../..');

function stubModule(filename, exports) {
  const m = new Module(filename);
  m.filename = filename;
  m.paths = Module._nodeModulePaths(path.dirname(filename));
  m.exports = exports;
  m.loaded = true;
  require.cache[filename] = m;
  return m;
}

// Stub RN-touching deps before harness compiles client.ts.
stubModule(path.join(ROOT, 'src/utils/apiClient.ts'), {
  __esModule: true,
  default: {
    get: async () => ({ ok: true, status: 200, data: {}, error: null, rid: null }),
    post: async () => ({ ok: true, status: 200, data: {}, error: null, rid: null }),
  },
});
stubModule(path.join(ROOT, 'utils/apiBase.ts'), {
  __esModule: true,
  API_BASE: 'http://app.test',
  SKELETON_API_BASE: 'http://engine.test',
  skeletonApi: (p) => `http://engine.test${p.startsWith('/') ? p : `/${p}`}`,
  api: (p) => `http://app.test${p.startsWith('/') ? p : `/${p}`}`,
});

const { load } = require('../skeleton-forge/harness.cjs');
const C = load('src/forgeOperator/client.ts');

test('skeletonPath joins /api/skeleton with relative or absolute routes', () => {
  assert.equal(C.skeletonPath('eras'), '/api/skeleton/eras');
  assert.equal(C.skeletonPath('/beats'), '/api/skeleton/beats');
  assert.equal(C.skeletonPath('/plan'), '/api/skeleton/plan');
  assert.equal(C.APP_SKELETON_API, '/api/skeleton');
});

test('enginePath builds absolute URLs against a base', () => {
  assert.equal(
    C.enginePath('http://engine.test', '/api/v1/gameforge/run'),
    'http://engine.test/api/v1/gameforge/run',
  );
  assert.equal(
    C.enginePath('http://engine.test/', 'gameforge/intake'),
    'http://engine.test/api/v1/gameforge/intake',
  );
  assert.equal(
    C.enginePath('http://engine.test', '/api/v1/gameforge/intake'),
    'http://engine.test/api/v1/gameforge/intake',
  );
  assert.equal(C.ENGINE_API_V1, '/api/v1');
});

test('mergeSealHeaders adds seal and actor weight without inventing secrets', () => {
  assert.deepEqual(C.mergeSealHeaders(null), {});
  assert.deepEqual(C.mergeSealHeaders({}), {});
  assert.deepEqual(C.mergeSealHeaders({ seal: '  ' }), {});
  assert.deepEqual(C.mergeSealHeaders({ seal: 'abc' }), { 'x-gf-seal': 'abc' });
  assert.deepEqual(
    C.mergeSealHeaders({ seal: 'tok', actorWeight: 7 }, { Accept: 'application/json' }),
    { Accept: 'application/json', 'x-gf-seal': 'tok', 'x-gf-actor-weight': '7' },
  );
  assert.deepEqual(
    C.mergeSealHeaders({ seal: null, actorWeight: '3' }),
    { 'x-gf-actor-weight': '3' },
  );
  // empty actor weight is omitted
  assert.deepEqual(C.mergeSealHeaders({ seal: 'x', actorWeight: '' }), { 'x-gf-seal': 'x' });
});

test('buildPlanBody drops empties and clamps vision', () => {
  assert.deepEqual(C.buildPlanBody({}), {});
  assert.deepEqual(C.buildPlanBody({ vision: '', era: null }), {});
  assert.deepEqual(
    C.buildPlanBody({ vision: 'raid', era: 'extraction_now', blend: ['a', 'b'], t: 0.4 }),
    { vision: 'raid', era: 'extraction_now', blend: ['a', 'b'], t: 0.4 },
  );
  assert.deepEqual(C.buildPlanBody({ blend: ['only-one'] }), {});
  const long = 'x'.repeat(5000);
  assert.equal(C.buildPlanBody({ vision: long }).vision.length, 4000);
});

test('buildRunBody and buildIntakeBody shape sealed engine payloads', () => {
  const run = C.buildRunBody({
    vision: 'forge a raid',
    target: 'godot',
    playtest: 'auto',
    repair_mode: 'apply',
    era: 'extraction_now',
    archetype: 'vision',
    answers: { pace: 'fast' },
  });
  assert.deepEqual(run, {
    vision: 'forge a raid',
    target: 'godot',
    playtest: 'auto',
    repair_mode: 'apply',
    include_files: false,
    era: 'extraction_now',
    archetype: 'vision',
    answers: { pace: 'fast' },
  });
  assert.equal(C.buildRunBody({
    vision: 'x', target: 'json', playtest: 'off', repair_mode: 'suggest', include_files: true,
  }).include_files, true);

  const intake = C.buildIntakeBody({
    answers: { mood: 'grim' },
    target: 'yaml',
    playtest: 'require',
    repair_mode: 'suggest',
    archetype: 'auto',
  });
  assert.deepEqual(intake, {
    answers: { mood: 'grim' },
    target: 'yaml',
    playtest: 'require',
    repair_mode: 'suggest',
    archetype: 'auto',
  });
  assert.deepEqual(
    C.buildIntakeBody({ answers: null, target: 'godot', playtest: 'off', repair_mode: 'apply' }).answers,
    {},
  );
});

test('operatorErrorFromApi maps ApiResult failures via toOperatorError', () => {
  assert.equal(C.operatorErrorFromApi(null), null);
  assert.equal(C.operatorErrorFromApi({ ok: true, status: 200, error: null, data: {}, rid: null }), null);

  const sealed = C.operatorErrorFromApi(
    { ok: false, status: 401, error: 'unauthorized', data: { error: { type: 'Auth', code: 'API.AUTH', message: 'invalid seal', context: {} } }, rid: 'r1' },
    { sealed: true, sealPresent: false },
  );
  assert.equal(sealed.kind, 'seal_missing');
  assert.equal(sealed.requestId, 'r1');

  const offline = C.operatorErrorFromApi(
    { ok: false, status: 0, error: 'timeout', data: null, rid: null },
  );
  assert.equal(offline.kind, 'timeout');
});
