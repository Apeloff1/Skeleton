// B040 S2/S3/S6 offline tests (Coder Lead). Run: node --test artifacts/carrol/b040/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DIMS, passes, validateResult, caseStatus, makeBaseline, compareToBaseline,
  runCase, runSet, scoreEditability, toFailureExport } from './arena_lib.mjs';
const here = new URL('.', import.meta.url);
const load = f => JSON.parse(readFileSync(new URL(f, here)));
const thr = { correctness: '>= 1', editability: '>= 0.8', latency: '<= 300', cost: '<= 0.50', safety: '== 0' };
const CASE = { case_id: 'B040-PLAT-001', version: 1, seed: 4001, brief: { title: 'Coin Hopper', genre: 'platformer' },
  dimensions: Object.fromEntries(DIMS.map(d => [d, { metric: d, pass_if: thr[d] }])) };
const sc = (v, p) => ({ value: v, passed: p });
const RESULT = { run_id: 'r1', set_version: 1, candidate: 'cand-a', git_sha: '9c4481e4', started_at: 't',
  cases: [{ case_id: 'B040-PLAT-001', version: 1, seed: 4001, status: 'passed', build_id: 'b1',
    scores: { correctness: sc(1, true), editability: sc(null, null), latency: sc(100, true), cost: sc(0.2, true), safety: sc(0, true) } }] };

test('S2-01 result + baseline schemas require all five dimensions', () => {
  assert.deepEqual(load('eval_result.schema.json').$defs.case_result.properties.scores.required, DIMS);
  assert.deepEqual(load('eval_baseline.schema.json').properties.tolerance.required, DIMS);
});
test('S2-02 validateResult accepts a good result and flags a broken one', () => {
  assert.deepEqual(validateResult(RESULT), []);
  const bad = structuredClone(RESULT); delete bad.cases[0].scores.safety; bad.git_sha = 'XYZ';
  const errs = validateResult(bad);
  assert.ok(errs.includes('git_sha') && errs.some(e => e.startsWith('dims')));
});
test('S2-03 passes() thresholds and null handling', () => {
  assert.equal(passes('>= 0.8', 0.8), true); assert.equal(passes('<= 300', 301), false);
  assert.equal(passes('== 0', 0), true); assert.equal(passes('>= 1', null), null);
  assert.throws(() => passes('> 1', 1));
});
test('S2-04 safety failure is a hard gate (AC5)', () => {
  const s = { ...RESULT.cases[0].scores, safety: sc(1, false) };
  assert.equal(caseStatus(s), 'failed');
});
test('S2-05 baseline round-trip and regression detection', () => {
  const tol = { correctness: 0, editability: 0.05, latency: 0.2, cost: 0.2, safety: 0 };
  const b = makeBaseline(RESULT, tol);
  assert.deepEqual(Object.keys(b.cases), ['B040-PLAT-001@1']);
  assert.deepEqual(compareToBaseline(RESULT, b), []);
  const worse = structuredClone(RESULT); worse.cases[0].scores.latency.value = 121; worse.cases[0].scores.safety.value = 1;
  assert.deepEqual(compareToBaseline(worse, b).map(r => r.dimension).sort(), ['latency', 'safety']);
});

function fakeApi(statuses, { createStatus = 200 } = {}) {
  let i = 0; const calls = [];
  const fetch = async (url, init) => {
    calls.push([init.method, url]);
    const ok = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
    if (url.endsWith('/galaxy-studio/create')) return ok({ build_id: 'b-1' }, createStatus);
    if (url.endsWith('/galaxy-studio/start-build')) return ok({});
    return ok(statuses[Math.min(i++, statuses.length - 1)]);
  };
  return { fetch, calls };
}
const clock = () => { let t = 0; return { now: () => t, sleep: async ms => { t += ms; } }; };

test('S3-01 runner scores correctness + latency through create -> start-build -> status', async () => {
  const api = fakeApi([{ status: 'building' }, { status: 'completed', file_count: 7 }]);
  const c = clock();
  const r = await runCase(CASE, { fetch: api.fetch, baseUrl: 'http://x/api', ...c, pollMs: 5000 });
  assert.equal(r.status, 'passed'); assert.equal(r.build_id, 'b-1');
  assert.deepEqual(r.scores.correctness, { value: 1, passed: true, reason: 'status=completed' });
  assert.equal(r.scores.latency.value, 5); assert.equal(r.scores.cost.passed, null);
  assert.deepEqual(api.calls.map(x => x[0]), ['POST', 'POST', 'GET', 'GET']);
});
test('S3-02 runner fails correctness on zero files and on timeout', async () => {
  const r1 = await runCase(CASE, { fetch: fakeApi([{ status: 'completed', file_count: 0 }]).fetch, baseUrl: '', ...clock() });
  assert.equal(r1.status, 'failed');
  const r2 = await runCase(CASE, { fetch: fakeApi([{ status: 'building' }]).fetch, baseUrl: '', ...clock(), timeoutS: 20 });
  assert.equal(r2.scores.correctness.reason, 'status=timeout'); assert.equal(r2.scores.latency.passed, false);
});
test('S3-03 HTTP errors become status=error without leaking bodies', async () => {
  const r = await runCase(CASE, { fetch: fakeApi([], { createStatus: 500 }).fetch, baseUrl: '', ...clock() });
  assert.equal(r.status, 'error'); assert.equal(r.scores.correctness.reason, 'HTTP 500 on /galaxy-studio/create');
});
test('S3-04 runSet output validates against the result contract', async () => {
  const out = await runSet([CASE], { run_id: 'r2', set_version: 1, candidate: 'c', git_sha: 'abcdef1', started_at: 't' },
    { fetch: fakeApi([{ status: 'completed', file_count: 1 }]).fetch, baseUrl: '', ...clock() });
  assert.deepEqual(validateResult(out), []);
});

test('S6-01 editability ratio counts only applied edits that keep the build green', () => {
  assert.deepEqual(scoreEditability(CASE, []), { value: null, passed: null, reason: 'no edit API (B020) yet' });
  const e = [{ applied: true, build_ok: true }, { applied: true, build_ok: false }, { applied: true, build_ok: true },
    { applied: true, build_ok: true }, { applied: true, build_ok: true }];
  assert.deepEqual(scoreEditability(CASE, e), { value: 0.8, passed: true });
});
test('S6-02 failure export lists failed dims; safety failures are not repairable', () => {
  const r = structuredClone(RESULT);
  r.cases.push({ case_id: 'B040-SAFE-001', version: 1, seed: 4003, status: 'failed', build_id: null,
    scores: { correctness: sc(1, true), editability: sc(null, null), latency: sc(9, true), cost: sc(0.1, true), safety: sc(2, false) } });
  r.cases.push({ case_id: 'B040-PUZ-001', version: 1, seed: 4002, status: 'failed', build_id: 'b2',
    scores: { correctness: sc(0, false), editability: sc(null, null), latency: sc(400, false), cost: sc(null, null), safety: sc(0, true) } });
  const x = toFailureExport(r);
  const schema = load('failure_export.schema.json');
  for (const k of schema.required) assert.ok(k in x, k);
  assert.equal(x.format, schema.properties.format.const);
  assert.deepEqual(x.failures.map(f => [f.case_id, f.repairable]), [['B040-SAFE-001', false], ['B040-PUZ-001', true]]);
  assert.deepEqual(x.failures[1].failed_dimensions.map(f => f.dimension), ['correctness', 'latency']);
});
