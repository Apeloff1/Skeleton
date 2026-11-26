'use strict';
// Pure view-model for the forge-gateway new-game flow. Run: yarn test:forge-gateway
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');

const m = load('src/forgeGateway/model.ts');

test('validateBrief mirrors the gateway rules', () => {
  assert.equal(m.validateBrief('   '), 'Describe the game you want to build.');
  assert.match(m.validateBrief('x'.repeat(m.MAX_BRIEF_CHARS + 1)), /under 4000/);
  assert.equal(m.validateBrief('  A small platformer  '), null);
});

test('summarise maps queued, running, success and failures', () => {
  assert.equal(m.summarise(null).phase, 'queued');
  const running = m.summarise({ execution_id: 'e', status: 'running', progress: 0.42, message: 'materialising' });
  assert.deepEqual([running.phase, running.percent, running.stage], ['running', 42, 'materialising']);
  const done = m.summarise({ execution_id: 'e', status: 'succeeded', progress: 1, result: {
    ok: true, spec: { title: 'Fox Roofs', genre: 'top_down_shooter' }, proof: 'CORE_LOOP_OK', playtest: { status: 'passed' }, stubbed: ['music'] } });
  assert.deepEqual([done.phase, done.percent, done.title, done.genre, done.proof, done.playtest, done.stubbed],
    ['succeeded', 100, 'Fox Roofs', 'top down shooter', 'CORE_LOOP_OK', 'passed', ['music']]);
  const unproven = m.summarise({ execution_id: 'e', status: 'succeeded', result: { ok: false, error: 'core loop did not print' } });
  assert.deepEqual([unproven.phase, unproven.error], ['failed', 'core loop did not print']);
  const failed = m.summarise({ execution_id: 'e', status: 'failed', error: 'timeout' });
  assert.deepEqual([failed.phase, failed.error], ['failed', 'timeout']);
  assert.equal(m.summarise({ execution_id: 'e', status: 'running', progress: 7 }).percent, 100);
  assert.equal(m.summarise({ execution_id: 'e', status: 'running', progress: Number.NaN }).percent, 0);
});

test('polling backoff, idempotency keys and error copy', () => {
  assert.equal(m.nextPollDelay(0), 600);
  assert.equal(m.nextPollDelay(50), 2000);
  assert.equal(m.nextPollDelay(0, 7), 7000);
  const key = m.newIdempotencyKey(() => 0.5, () => 1_700_000_000_000);
  assert.match(key, /^ng-[a-z0-9]+-[a-z0-9]{16}$/);
  assert.ok(key.length >= 8 && key.length <= 128);
  assert.match(m.gatewayErrorMessage(401, null), /Sign in/);
  assert.match(m.gatewayErrorMessage(429, null), /Too many/);
  assert.equal(m.gatewayErrorMessage(422, 'brief is required'), 'brief is required');
  assert.doesNotMatch(m.gatewayErrorMessage(500, 'Traceback secret'), /Traceback/);
  assert.match(m.gatewayErrorMessage(0, null), /offline/);
});
