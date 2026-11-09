'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const noseal = require('./fixtures/run_noseal.json');
const badmode = require('./fixtures/run_badmode.json');
const commands = require('./fixtures/commands.json');

const E = load('src/forgeOperator/errors.ts');

test('extractMessage: string, envelope, detail shapes, pydantic, fallbacks', () => {
  assert.deepEqual(E.extractMessage('plain'), { message: 'plain' });
  assert.equal(E.extractMessage(null).message, '');
  assert.equal(E.extractMessage(42).message, '');
  assert.equal(E.extractMessage([]).message, '');

  const env = E.extractMessage(noseal.body);
  assert.equal(env.message, 'invalid seal');
  assert.equal(env.code, 'API.AUTH');
  assert.deepEqual(env.context, {});

  assert.equal(E.extractMessage({ error: { type: 'X', code: 'C' } }).message, 'X');
  assert.equal(E.extractMessage({ error: 'top-level string' }).message, 'top-level string');
  assert.equal(E.extractMessage(badmode.body).message, 'playtest must be one of auto, off, require');

  const det = E.extractMessage({ detail: { error: 'charter_denied', reason: 'weight too low' } });
  assert.equal(det.message, 'charter_denied: weight too low');
  assert.equal(det.code, 'charter_denied');
  assert.equal(E.extractMessage({ detail: { message: 'only msg' } }).message, 'only msg');
  assert.equal(E.extractMessage({ detail: { code: 'C', reason: 'r' } }).message, 'C: r');

  const pyd = E.extractMessage({
    detail: [
      { loc: ['body', 'vision'], msg: 'field required' },
      { loc: ['query', 'mode'], msg: 'not a valid' },
      'bare',
    ],
  });
  assert.equal(pyd.message, 'vision: field required; query.mode: not a valid; bare');

  assert.equal(E.extractMessage({ message: 'bare field' }).message, 'bare field');
  assert.equal(E.extractMessage({ other: true }).message, '');
});

test('toOperatorError kind matrix: transport, seal, charter, cockpit, http', () => {
  assert.equal(E.toOperatorError({ status: 0, error: 'timeout', data: null }).kind, 'timeout');
  assert.equal(E.toOperatorError({ status: 0, error: 'circuit_open', data: null }).kind, 'circuit_open');
  assert.equal(E.toOperatorError({ status: 0, error: 'aborted', data: null }).kind, 'aborted');
  assert.equal(E.toOperatorError({ status: 0, error: 'network_error', data: null }).kind, 'offline');
  assert.equal(E.toOperatorError({ status: 0, error: 'weird', data: null }).kind, 'offline');

  const miss = E.toOperatorError({ status: 401, error: null, data: noseal.body }, { sealed: true, sealPresent: false });
  assert.equal(miss.kind, 'seal_missing');
  assert.equal(miss.message, 'invalid seal');
  assert.equal(miss.code, 'API.AUTH');
  assert.match(miss.hint, /Paste an x-gf-seal/);

  assert.equal(E.toOperatorError({ status: 401, data: noseal.body }, { sealed: true, sealPresent: true }).kind, 'seal_invalid');
  assert.equal(E.toOperatorError({ status: 401, data: noseal.body }, { sealed: false }).kind, 'seal_invalid');

  assert.equal(E.toOperatorError({ status: 403, data: { detail: 'nope' } }, { ops: true }).kind, 'ops_unauthorized');
  assert.equal(
    E.toOperatorError({ status: 403, data: { detail: { error: 'charter_denied', reason: 'weight' } } }).kind,
    'charter_denied',
  );
  assert.equal(E.toOperatorError({ status: 403, data: { detail: 'Charter blocked' } }).kind, 'charter_denied');
  assert.equal(E.toOperatorError({ status: 403, data: { detail: 'forbidden' } }, { sealed: true }).kind, 'seal_invalid');
  assert.equal(E.toOperatorError({ status: 403, data: { detail: 'forbidden' } }).kind, 'ops_unauthorized');

  assert.equal(E.toOperatorError({ status: 503, data: { detail: 'seal unavailable' } }).kind, 'seal_unavailable');
  assert.equal(E.toOperatorError({ status: 503, data: { detail: 'boot incomplete' } }).kind, 'not_ready');
  assert.equal(E.toOperatorError({ status: 404, data: { detail: 'gone' } }).kind, 'not_found');

  const rej = commands['BIND ARCHETYPE dragon'];
  const ck = E.toOperatorError({ status: rej.status, data: rej.body, rid: 'req-1' });
  assert.equal(ck.kind, 'cockpit');
  assert.equal(ck.code, 'CTX.COCKPIT');
  assert.equal(ck.requestId, 'req-1');
  assert.ok(ck.context.known.includes('auto'));
  assert.match(ck.hint, /verb grammar/);

  const bad = E.toOperatorError({ status: badmode.status, data: badmode.body });
  assert.equal(bad.kind, 'validation');
  assert.match(bad.message, /playtest must be one of/);
  assert.equal(E.toOperatorError({ status: 400, data: { detail: 'bad' } }).kind, 'validation');
  assert.equal(E.toOperatorError({ status: 500, data: { detail: 'boom' } }).kind, 'server');
  assert.equal(E.toOperatorError({ status: 418, data: null }).kind, 'server');

  const prefer = E.toOperatorError({ status: 500, error: 'transport', data: { message: 'from body' } });
  assert.equal(prefer.message, 'from body');
  assert.equal(E.toOperatorError({ status: 502, error: 'gateway', data: null }).message, 'gateway');
  assert.equal(E.toOperatorError({ status: 502, error: null, data: null }).message, 'HTTP 502');
  assert.equal(E.toOperatorError({ status: 0, error: null, data: null }).message, 'request failed');
});

test('isTransient, knownValues, operatorErrorFromException', () => {
  for (const kind of ['timeout', 'offline', 'circuit_open', 'not_ready']) {
    assert.equal(E.isTransient({ kind, status: 0, message: '', hint: '' }), true, kind);
  }
  for (const kind of ['validation', 'server', 'cockpit', 'seal_missing', 'aborted']) {
    assert.equal(E.isTransient({ kind, status: 0, message: '', hint: '' }), false, kind);
  }

  assert.deepEqual(E.knownValues({ context: { known: ['a', 2] } }), ['a', '2']);
  assert.deepEqual(E.knownValues({ context: { known: null } }), []);
  assert.deepEqual(E.knownValues({ context: {} }), []);
  assert.deepEqual(E.knownValues(null), []);
  assert.deepEqual(E.knownValues(undefined), []);

  const fromErr = E.operatorErrorFromException(new Error('boom'));
  assert.equal(fromErr.kind, 'server');
  assert.equal(fromErr.status, 0);
  assert.equal(fromErr.message, 'boom');
  assert.match(fromErr.hint, /backend failed/i);
  assert.equal(E.operatorErrorFromException('str').message, 'str');
  assert.equal(E.operatorErrorFromException(null).message, 'unexpected error');
  assert.equal(E.operatorErrorFromException('').message, 'unexpected error');
});
