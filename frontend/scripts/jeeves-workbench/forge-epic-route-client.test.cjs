/** Transport fixtures validate the source-only client, not native or model quality. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const filename = path.resolve(__dirname, '../../src/product/gameFrontierAuthoringClient.ts');
const request = { layer_ids: ['ground', 'sky'], connectors: [{ connector_id: 'lift',
  from: { layer: 'ground', x: 1, y: 0 }, to: { layer: 'sky', x: 1, y: 0 }, mode: 'elevator', bidirectional: true }],
itineraries: [{ journey_id: 'Crossing', start: { layer: 'ground', x: 0, y: 0 },
  goal: { layer: 'sky', x: 1, y: 0 }, require_alternate: false }] };
const fixture = { schema: 'skeleton.forge.epic_interlayer_reference.v1', project_id: 'owned-project',
  project_sha256: 'a'.repeat(64), source_version: 7, layer_ids: ['ground', 'sky'],
  layer_source_sha256: { ground: 'b'.repeat(64), sky: 'c'.repeat(64) },
  connectors: [{ connector_id: 'lift', mode: 'elevator', distance_m: 12 }],
  journey_count: 1, passed_count: 1, failed_count: 0,
  journeys: [{ journey_id: 'Crossing', start: ['ground', 0, 0], goal: ['sky', 1, 0], require_alternate: false,
    primary: { reachable: true, steps: 2, transfers: 1, connector_ids: ['lift'], path_sha256: 'd'.repeat(64),
      sample: [['ground', 0, 0], ['ground', 1, 0], ['sky', 1, 0]], sample_truncated: false },
    alternate: null, passed: true, failure: null }], receipt_sha256: 'e'.repeat(64),
  verified_against_authoritative_source: true, native_engine_executed: false,
  transport_actions_applied: false, release_certified: false, source_reference_only: true };
function client(change = () => {}) {
  const response = structuredClone(fixture); change(response); const calls = [];
  const api = { post: async (route, body, options) => { calls.push({ route, body, options }); return { ok: true, data: response }; } };
  const module = { exports: {} };
  class ProtocolError extends Error { constructor(message, fields) { super(message); Object.assign(this, fields); } }
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  new Function('module', 'exports', 'require', code)(module, module.exports, name => {
    if (name === '../utils/apiClient') return { default: api };
    if (name === '../auth/gameforgeAuth') return { authHeaders: () => ({ Authorization: 'Bearer declared-fixture' }),
      getAuthToken: () => 'declared-fixture', getAuthEpoch: () => 1, initializeStoredToken: async () => {} };
    if (name === './chatErrors') return { ChatClientError: ProtocolError, chatApiError: (_response, message) => new Error(message) };
    if (name === './gameLearningClient') return { learningRequestKey: () => 'declared-request-key' };
    if (name === '../features/Jeeves/forgeParameters/forgeQueuedSave') return {
      cloneForgeEditInput: () => { throw new Error('Read-only Epic audit cannot prepare a save.'); },
    };
    throw new Error('Unexpected client dependency: ' + name);
  });
  return { api: module.exports, calls };
}
test('Epic audit uses the existing authenticated pure endpoint and a bound typed source report', async () => {
  const h = client(); const result = await h.api.auditForgeEpicRoutes('owned-project', request);
  assert.equal(result.native_engine_executed, false);
  assert.deepEqual(h.calls.map(call => call.route), ['/api/game-frontier-authoring/projects/owned-project/epic-routes/audit']);
  assert.deepEqual(h.calls[0].body, request);
  assert.equal(h.calls[0].options.headers.Authorization, 'Bearer declared-fixture');
  assert.equal(h.calls[0].options.retries, 0);
});
test('unknown root fields and excessive source scopes are rejected before any HTTP request', async () => {
  for (const body of [{ ...request, provider: 'hosted' }, { ...request, layer_ids: [] },
    { ...request, layer_ids: ['ground', 'ground'] }, { ...request, connectors: Array(65).fill({}) },
    { ...request, itineraries: Array(33).fill({}) }]) {
    const h = client(); await assert.rejects(h.api.auditForgeEpicRoutes('owned-project', body)); assert.equal(h.calls.length, 0);
  }
});
test('foreign identity, unverified source and native/release claims fail the protocol guard', async () => {
  for (const change of [r => { r.project_id = 'foreign'; }, r => { r.source_version = 0; },
    r => { r.verified_against_authoritative_source = false; }, r => { r.source_reference_only = false; },
    r => { r.native_engine_executed = true; }, r => { r.release_certified = true; },
    r => { r.transport_actions_applied = true; }]) {
    const h = client(change); await assert.rejects(h.api.auditForgeEpicRoutes('owned-project', request), /replay contract/);
  }
});
test('different scenarios, layers, connectors and inconsistent witnesses cannot replace the requested audit', async () => {
  for (const change of [r => { r.layer_ids.reverse(); }, r => { r.layer_source_sha256.ground = 'broken'; },
    r => { r.connectors[0].connector_id = 'unrequested'; }, r => { r.journeys[0].journey_id = 'another'; },
    r => { r.journeys[0].primary.path_sha256 = null; }, r => { r.journeys[0].primary.transfers = 2; },
    r => { r.journeys[0].start[1] = 6; }, r => { r.passed_count = 0; r.failed_count = 1; }]) {
    const h = client(change); await assert.rejects(h.api.auditForgeEpicRoutes('owned-project', request), /replay contract/);
  }
});
test('an honestly unreachable source route remains a valid failed audit, with no native success', async () => {
  const h = client(r => { r.connectors = []; r.passed_count = 0; r.failed_count = 1;
    Object.assign(r.journeys[0], { passed: false, failure: 'no_source_tile_path', primary: {
      reachable: false, steps: null, transfers: 0, connector_ids: [], path_sha256: null, sample: [], sample_truncated: false } }); });
  const result = await h.api.auditForgeEpicRoutes('owned-project', { ...request, connectors: [] });
  assert.equal(result.failed_count, 1); assert.equal(result.journeys[0].primary.reachable, false);
});
