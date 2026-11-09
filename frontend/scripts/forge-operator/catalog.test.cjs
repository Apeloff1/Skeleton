'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const { eras } = require('./fixtures/eras.json');
const { beats } = require('./fixtures/beats.json');
const { generations } = require('./fixtures/generations.json');
const intake = require('./fixtures/intake.json');
const noseal = require('./fixtures/run_noseal.json');
const badmode = require('./fixtures/run_badmode.json');
const commands = require('./fixtures/commands.json');

const K = load('src/forgeOperator/catalog.ts');
const E = load('src/forgeOperator/errors.ts');

test('era metrics, extents and normalisation', () => {
  const ext = K.eraExtents(eras);
  for (const { key } of K.ERA_METRICS) assert.ok(ext[key].min <= ext[key].max, key);
  const now = eras.find((e) => e.id === 'extraction_now');
  assert.equal(K.eraMetric(now, 'trash'), 1.1);
  assert.equal(K.normalise(5, { min: 5, max: 5 }), 0.5);
  assert.equal(K.normalise(NaN, { min: 0, max: 1 }), 0);
});

test('filter, sort and compare eras', () => {
  assert.ok(K.filterEras(eras, 'SOULS').some((e) => e.id === 'soulslike'));
  assert.equal(K.filterEras(eras, '  ').length, eras.length);
  const sorted = K.sortEras(eras, 'primary_dps');
  for (let i = 1; i < sorted.length; i += 1) assert.ok(sorted[i - 1].primary_dps >= sorted[i].primary_dps);
  const a = eras[0];
  const delta = K.compareEras(a, a);
  assert.ok(delta.every((d) => d.ratio === null || d.ratio === 1));
  const b = eras[1];
  const mid = K.blendEstimate(a, b, 0.5);
  assert.equal(mid.primary_dps, (a.primary_dps + b.primary_dps) / 2);
  assert.equal(K.blendEstimate(a, b, 7).speed, b.speed, 't is clamped');
  const groups = K.philosophyGroups(eras);
  assert.equal(groups.reduce((n, g) => n + g.eras.length, 0), eras.length);
});

test('generation ladder follows hardware order', () => {
  assert.deepEqual(K.generationLadder([...generations].reverse()).map((g) => g.key), ['8bit', '16bit', 'early3d', '64bit', 'earlyhd', 'modern', 'nextgen']);
});

test('beat progress and cleaning match engine intake rules', () => {
  const p0 = K.beatProgress(beats, {});
  assert.equal(p0.total, 11, 'era_explicit is not required');
  const answers = K.seededAnswers(beats, 42);
  assert.deepEqual(K.seededAnswers(beats, 42), answers, 'deterministic');
  assert.equal(answers.era_explicit, 'unspecified');
  assert.equal(K.beatProgress(beats, answers).missing.length, 0);
  const cleaned = K.cleanAnswers(beats, { ...answers, bogus: 'x', pace: 'not-an-option' });
  assert.ok(!('era_explicit' in cleaned));
  assert.ok(!('bogus' in cleaned));
  assert.ok(!('pace' in cleaned));
});

test('ballot shares from a real intake', () => {
  const shares = K.ballotShares(intake.intake.ballots);
  assert.equal(shares[0].era, 'soulslike');
  assert.ok(Math.abs(shares.reduce((n, s) => n + s.share, 0) - 1) < 1e-9);
  assert.deepEqual(K.ballotShares(null), []);
});

test('execution tones and summary put human-needed work first', () => {
  const mk = (id, over) => ({ operationId: id, state: 'done', confidence: 'high', pending: false, executorBound: true, receiptPresent: true, anomalyCount: 0, anomalies: [], evidenceSha256: '', writable: false, ...over });
  const list = [
    mk('a'),
    mk('b', { pending: true }),
    mk('c', { pending: true, executorBound: false, state: 'queued', confidence: 'low' }),
    mk('d', { anomalyCount: 1, anomalies: ['receipt_missing'] }),
  ];
  assert.deepEqual(K.sortExecutions(list).map((e) => e.operationId), ['d', 'c', 'b', 'a']);
  const s = K.summariseExecutions(list);
  assert.deepEqual(s.byTone, { ok: 1, pending: 1, stuck: 1, anomalous: 1 });
  assert.equal(s.lowConfidence, 1);
  assert.deepEqual(s.anomalies, [{ code: 'receipt_missing', count: 1 }]);
});

test('operator errors: seal, validation, cockpit, transport', () => {
  const seal = E.toOperatorError({ status: noseal.status, error: null, data: noseal.body }, { sealed: true, sealPresent: false });
  assert.equal(seal.kind, 'seal_missing');
  assert.equal(seal.message, 'invalid seal');
  assert.equal(E.toOperatorError({ status: 401, data: noseal.body }, { sealed: true, sealPresent: true }).kind, 'seal_invalid');
  const bad = E.toOperatorError({ status: badmode.status, data: badmode.body });
  assert.equal(bad.kind, 'validation');
  assert.match(bad.message, /playtest must be one of/);
  const rej = commands['BIND ARCHETYPE dragon'];
  const ck = E.toOperatorError({ status: rej.status, data: rej.body });
  assert.equal(ck.kind, 'cockpit');
  assert.ok(E.knownValues(ck).includes('auto'));
  assert.equal(E.toOperatorError({ status: 0, error: 'timeout', data: null }).kind, 'timeout');
  assert.equal(E.isTransient(E.toOperatorError({ status: 0, error: 'network_error', data: null })), true);
  assert.equal(E.toOperatorError({ status: 503, data: { detail: 'seal unavailable' } }).kind, 'seal_unavailable');
  assert.equal(E.toOperatorError({ status: 403, data: { detail: { error: 'charter_denied', reason: 'weight' } } }).kind, 'charter_denied');
  const pyd = E.extractMessage({ detail: [{ loc: ['body', 'vision'], msg: 'field required' }] });
  assert.equal(pyd.message, 'vision: field required');
  assert.equal(E.operatorErrorFromException(new Error('boom')).message, 'boom');
});
