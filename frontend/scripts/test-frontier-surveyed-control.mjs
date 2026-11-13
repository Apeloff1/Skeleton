import assert from 'node:assert/strict';
import { test } from 'node:test';
import { initialSurveyState, applySurveyAction, validateSurvey, hasUnapprovedChanges } from '../src/product/frontierSurveyedControl.ts';

const op = 'ops-ingrid';
const sighting = { sighting_id: 's1', control_point_id: 'cp-7', true_bearing_deg: 45, distance_m: 120, uncertainty_m: 0.5 };
const baseline = { baseline_id: 'bl-1', epoch: '2026-10-24', instrument: 'Total station', surveyor: 'Ingrid', notes: '' };

function run(state, ...actions) {
  for (const a of actions) {
    const r = applySurveyAction(state, a, op, 1);
    assert.equal(r.error, null, `${a.type}: ${r.error}`);
    state = r.state;
  }
  return state;
}
const ready = () => run(initialSurveyState(), { type: 'edit_baseline', patch: baseline }, { type: 'upsert_sighting', sighting });

test('validation catches bad sighting inputs and baseline metadata', () => {
  const issues = validateSurvey({ baseline: { ...ready().baseline, epoch: 'soon' }, sightings: [{ ...sighting, true_bearing_deg: 360, distance_m: 0 }, { ...sighting }] });
  const fields = issues.map(i => i.field);
  assert.ok(fields.includes('baseline.epoch'));
  assert.ok(fields.includes('sightings[0].true_bearing_deg'));
  assert.ok(fields.includes('sightings[0].distance_m'));
  assert.ok(fields.includes('sightings[1].sighting_id'));
  assert.deepEqual(validateSurvey(ready()), []);
});

test('nothing applies without submit + named operator approval', () => {
  let s = ready();
  assert.equal(s.approved, null);
  assert.match(applySurveyAction(s, { type: 'approve' }, op, 1).error, /Submit/);
  assert.match(applySurveyAction(s, { type: 'submit' }, '  ', 1).error, /operator/);
  assert.match(applySurveyAction(initialSurveyState(), { type: 'submit' }, op, 1).error, /Fix/);
  s = run(s, { type: 'submit' });
  assert.match(applySurveyAction(s, { type: 'upsert_sighting', sighting }, op, 1).error, /Withdraw/);
  s = run(s, { type: 'approve' });
  assert.equal(s.status, 'approved');
  assert.deepEqual(s.approved.sightings, [sighting]);
  assert.equal(hasUnapprovedChanges(s), false);
  assert.deepEqual(s.audit.map(a => a.action), ['edit', 'edit', 'submit', 'approve']);
});

test('reject needs a reason; revert restores the approved snapshot', () => {
  let s = run(ready(), { type: 'submit' });
  assert.match(applySurveyAction(s, { type: 'reject', reason: ' ' }, op, 1).error, /reason/);
  s = run(s, { type: 'reject', reason: 'bearing off' }, { type: 'submit' }, { type: 'approve' });
  s = run(s, { type: 'upsert_sighting', sighting: { ...sighting, distance_m: 999 } });
  assert.equal(s.status, 'draft'); assert.equal(hasUnapprovedChanges(s), true);
  assert.equal(s.approved.sightings[0].distance_m, 120);
  s = run(s, { type: 'revert' });
  assert.equal(s.status, 'approved'); assert.equal(s.sightings[0].distance_m, 120);
  assert.match(applySurveyAction(s, { type: 'submit' }, op, 1).error, /Nothing changed/);
  assert.equal(s.audit.find(a => a.action === 'reject').reason, 'bearing off');
});

test('datum cannot be changed away from WGS84', () => {
  const s = run(ready(), { type: 'edit_baseline', patch: { datum: 'NAD27' } });
  assert.equal(s.baseline.datum, 'WGS84');
});
