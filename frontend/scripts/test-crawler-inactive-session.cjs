'use strict';
// Backend owner-list projection regression. No crawler or HTTP request runs.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function load(file, imports = {}) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, file), 'utf8'), { fileName: file, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } });
  assert.equal(output.diagnostics.length, 0);
  const module = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])(id => { assert.ok(Object.hasOwn(imports, id), file + ': ' + id); return imports[id]; }, module, module.exports);
  return module.exports;
}
function inactive() {
  return { session_id: 'completed-owner-capture', title: 'Bounded owner capture', status: 'completed', version: 3,
    created_at: '2026-10-25T07:00:00.000Z', updated_at: '2026-10-25T07:01:00.000Z', seeds: ['https://example.com/'],
    limits: { max_requests: 1, max_documents: 1, max_total_bytes: 1048576, max_depth: 0 },
    counters: { requests: 1, bytes: 1256, documents: 1, failures: 0 }, frontier_count: 0, source_count: 1,
    consent_current: true, consent_expires_at: '2026-10-26T07:00:00.000Z', queue: [],
    automation: { enabled: false, state: 'not_authorized', epoch: 0, slices_started: 0, max_slices: 0,
      expires_at: null, next_run_at: null, stop_reason: null },
    worker: { active: false, quiescent: true, local: false, lease_until: null, confirmation: 'durable_completion', recovery_eligible: true },
    capabilities: { can_run: false, can_pause: false, can_resume: false, can_cancel: false, can_erase: true, can_automate: false } };
}
function fixture() {
  const calls = [], wire = { page: { ok: true, sessions: [inactive()], next_cursor: null } };
  const errors = load('src/product/chatErrors.ts');
  const client = load('src/product/crawlerClient.ts', {
    'expo-crypto': { CryptoDigestAlgorithm: { SHA256: 'SHA256' }, digestStringAsync: async () => { throw new Error('Unexpected export hashing'); } },
    '../utils/apiBase': { API_BASE: 'https://backend.test' },
    '../utils/apiClient': { __esModule: true, default: { get: async (url, options) => {
      calls.push({ url, options }); return { ok: true, status: 200, data: wire.page, error: null, rid: 'fixture-request' };
    } } },
    '../auth/gameforgeAuth': { getAuthToken: () => 'owner-fixture-token', authHeaders: () => ({ Authorization: 'Bearer owner-fixture-token' }) },
    './chatErrors': errors,
  });
  return { ...client, wire, calls };
}

test('owner list accepts an explicit inactive zero-budget automation projection and preserves null fields', async () => {
  const f = fixture();
  const page = await f.listCrawls();
  assert.equal(page.sessions.length, 1); assert.deepEqual(page.sessions[0].automation, inactive().automation);
  assert.equal(page.sessions[0].worker.confirmation, 'durable_completion');
  assert.equal(f.calls[0].url, '/api/dragon-academy/crawler/sessions?limit=32');
  assert.equal(f.calls[0].options.retries, 0);
});

test('inactive stopped and disabled projections retain finite zero values rather than inventing a grant', async () => {
  for (const state of ['disabled', 'stopped', 'not_authorized']) {
    const f = fixture(); f.wire.page.sessions[0].automation.state = state;
    const automation = (await f.listCrawls()).sessions[0].automation;
    assert.equal(automation.enabled, false); assert.equal(automation.epoch, 0); assert.equal(automation.max_slices, 0);
    assert.equal(automation.expires_at, null); assert.equal(automation.next_run_at, null); assert.equal(automation.stop_reason, null);
  }
});

test('malformed active grants remain rejected by the real crawler client parser', async () => {
  const active = { enabled: true, state: 'authorized', epoch: 1, slices_started: 0, max_slices: 1,
    expires_at: '2026-10-25T08:00:00.000Z', next_run_at: null, stop_reason: null };
  for (const patch of [{ max_slices: 0 }, { epoch: -1 }, { epoch: '1' }, { slices_started: 2 },
    { expires_at: 'not-a-timestamp' }, { next_run_at: 'not-a-timestamp' }, { stop_reason: { message: 'invalid' } }]) {
    const f = fixture(); f.wire.page.sessions[0].automation = { ...active, ...patch };
    await assert.rejects(f.listCrawls(), error => error.kind === 'protocol' && /automation authorization/.test(error.message));
  }
});
