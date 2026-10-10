'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const snapshot = require('./fixtures/snapshot.json');

const S = load('src/forgeOperator/cockpitSummary.ts');
const clone = (x) => JSON.parse(JSON.stringify(x));

test('summarizeSnapshot flattens fixture into operator readout', () => {
  const s = S.summarizeSnapshot(snapshot);
  assert.ok(s);
  assert.match(s.era, /arcade_golden_age/);
  assert.equal(s.fingerprint, snapshot.tensor.fingerprint);
  assert.match(s.dominant, /risk=/);
  assert.match(s.axesPreview, /risk=/);
  assert.match(s.blend, /arcade_golden_age → soulslike/);
  assert.equal(s.ledger.startsWith('h='), true);
  assert.equal(typeof s.historyCount, 'number');
});

test('summarizeSnapshot returns null without tensor', () => {
  assert.equal(S.summarizeSnapshot(null), null);
  assert.equal(S.summarizeSnapshot({}), null);
  assert.equal(S.summarizeSnapshot({ ledger: { height: 1, valid: true } }), null);
});

test('extractSnapshot reads envelope result and bare snapshot', () => {
  assert.equal(S.extractSnapshot(null), null);
  assert.ok(S.isCockpitSnapshot(snapshot));
  assert.equal(S.extractSnapshot(snapshot).tensor.era, snapshot.tensor.era);
  const envelope = { ok: true, verb: 'SNAPSHOT', result: snapshot };
  assert.equal(S.extractSnapshot(envelope).tensor.fingerprint, snapshot.tensor.fingerprint);
  assert.equal(S.extractSnapshot({ ok: true, verb: 'BIND', result: { era: 'x' } }), null);
});

test('asCommandEnvelope wraps snapshots and passes through envelopes', () => {
  const env = S.asCommandEnvelope({ ok: true, verb: 'ROLL', result: { index: 1, text: 'hi' } });
  assert.equal(env.verb, 'ROLL');
  assert.equal(env.ok, true);
  const wrapped = S.asCommandEnvelope(snapshot, 'STATUS');
  assert.equal(wrapped.verb, 'STATUS');
  assert.equal(wrapped.ok, true);
  assert.equal(S.asCommandEnvelope(null), null);
});

test('formatSnapshotChange and changeFieldLabel speak operator language', () => {
  assert.equal(S.changeFieldLabel('axis.risk'), 'risk');
  assert.equal(S.changeFieldLabel('helix.σ'), 'helix σ');
  assert.equal(S.changeFieldLabel('ledger.height'), 'ledger height');
  assert.match(
    S.formatSnapshotChange({ field: 'axis.risk', before: '0.700', after: '0.900', delta: 0.2 }),
    /risk 0\.700 → 0\.900 \(\+0\.200\)/,
  );
  assert.equal(
    S.formatSnapshotChange({ field: 'generation', before: '8bit', after: '16bit', delta: 0 }),
    'generation 8bit → 16bit',
  );
  assert.match(
    S.formatSnapshotChange({ field: 'ledger.height', before: '3', after: '5', delta: 2 }),
    /ledger height 3 → 5 \(\+2\)/,
  );
});

test('snapshotDiff + formatSnapshotChanges cover axis and categorical deltas', () => {
  const after = clone(snapshot);
  after.tensor.axes.risk = (after.tensor.axes.risk ?? 0) + 0.2;
  after.generation = after.generation === '8bit' ? '16bit' : '8bit';
  after.ledger.height += 2;
  const changes = S.snapshotDiff(snapshot, after);
  const labels = S.formatSnapshotChanges(changes);
  assert.ok(labels.some((l) => /^risk /.test(l)));
  assert.ok(labels.some((l) => /^generation /.test(l)));
  assert.ok(labels.some((l) => /^ledger height /.test(l)));
  assert.deepEqual(S.snapshotDiff(null, snapshot), []);
});

test('format helpers tolerate empty inputs', () => {
  assert.equal(S.formatDominant(null), '—');
  assert.equal(S.formatBlend(null), '—');
  assert.equal(S.formatOracle(null), '—');
  assert.equal(S.formatHelix(null), '—');
  assert.equal(S.formatLedger(null), '—');
  assert.equal(S.formatAxesPreview(null), '—');
  assert.equal(S.formatOracle({ index: 3, text: 'Maybe', faces: [], weight: 1, seed: 'x' }), '#3: Maybe');
  assert.match(S.formatLedger({ height: 4, head: 'abc', valid: false }), /INVALID/);
});

test('validationMessage blocks bad verbs and accepts SNAPSHOT', () => {
  assert.equal(S.validationMessage('SNAPSHOT'), null);
  assert.match(S.validationMessage('FLY away'), /unknown verb/i);
  assert.match(S.validationMessage(''), /empty/i);
});

test('explainCommandResult prefers describeResult', () => {
  const envelope = { ok: true, verb: 'SET', result: { axis: 'risk', value: 0.9 } };
  // spec looked up via parse — pass a minimal stand-in by loading commands
  const C = load('src/forgeOperator/commands.ts');
  const spec = C.parseCommand('SET AXIS risk 0.9').spec;
  assert.equal(S.explainCommandResult(envelope, spec, 'SET AXIS risk 0.9'), 'risk = 0.90');
  assert.equal(S.explainCommandResult(null, null, 'ROLL ORACLE'), 'ROLL ok');
});

test('historyA11yLabel includes status and change count', () => {
  const label = S.historyA11yLabel({
    id: 1,
    command: 'SET AXIS risk 0.9',
    ok: true,
    summary: 'risk = 0.90',
    changes: ['risk 0.700 → 0.900 (+0.200)'],
    at: 0,
  });
  assert.match(label, /SET AXIS risk 0\.9: ok, risk = 0\.90, 1 change/);
});

test('operatorTabs includes cockpit after beats', () => {
  const T = load('src/forgeOperator/operatorTabs.ts');
  assert.ok(T.OPERATOR_TABS.includes('cockpit'));
  const beatsIdx = T.OPERATOR_TABS.indexOf('beats');
  const cockpitIdx = T.OPERATOR_TABS.indexOf('cockpit');
  assert.ok(cockpitIdx === beatsIdx + 1);
  assert.equal(T.OPERATOR_TAB_LABELS.cockpit, 'Cockpit');
  assert.match(T.OPERATOR_TAB_HINTS.cockpit, /\/api\/skeleton\/cockpit/);
  assert.equal(T.parseOperatorTab('cockpit'), 'cockpit');
  assert.equal(T.parseOperatorTab('COCKPIT'), 'cockpit');
});
