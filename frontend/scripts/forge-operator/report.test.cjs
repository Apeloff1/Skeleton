'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const run = require('./fixtures/run.json');
const required = require('./fixtures/run_playtest_required.json');
const intake = require('./fixtures/intake.json');

const R = load('src/forgeOperator/runReport.ts');
const clone = (x) => JSON.parse(JSON.stringify(x));
const REQ = { vision: 'storm heist', target: 'godot', playtest: 'auto', repair_mode: 'suggest' };

test('stage timeline covers all ten canonical stages in order', () => {
  const t = R.stageTimeline(run);
  assert.deepEqual(t.map((s) => s.name), ['ingest', 'detect', 'tensor', 'lattice', 'oracle', 'forge', 'jeeves', 'sim', 'emit', 'seal']);
  assert.ok(t.every((s) => s.state === 'ok' || s.state === 'retried'));
  assert.equal(R.failedStage(run), null);
});

test('a required playtest that blocks emit is recovered from the stage error', () => {
  const t = R.stageTimeline(required);
  assert.equal(t.find((s) => s.name === 'emit').state, 'failed');
  assert.equal(t.find((s) => s.name === 'seal').state, 'not_run');
  const p = R.playtestVerdict(required, 'require');
  assert.equal(p.state, 'blocked');
  assert.equal(p.label, 'REQUIRED · UNAVAILABLE');
  assert.match(p.detail, /No Godot binary/);
  assert.equal(p.gating, true);
  const v = R.operatorVerdict(required, { playtest: 'require' });
  assert.equal(v.verdict, 'blocked');
  assert.match(v.reasons[0].text, /Stage "emit" failed/);
});

test('unavailable playtest on an auto run is a review, not a block', () => {
  const p = R.playtestVerdict(run, 'auto');
  assert.equal(p.state, 'unavailable');
  assert.equal(p.label, 'NOT RUN');
  assert.equal(p.binarySource, 'missing-godot-binary');
  const v = R.operatorVerdict(run, REQ);
  assert.equal(v.verdict, 'review');
  assert.ok(v.reasons.some((r) => /Playtest not run/.test(r.text)));
  assert.ok(v.reasons.some((r) => /4 file\(s\) passed with warnings/.test(r.text)));
  assert.ok(!v.reasons.some((r) => /Post-processing/.test(r.text)), 'ImportError postprocess is benign');
});

test('passing playtest + clean verification ships', () => {
  const p = clone(run);
  p.playtest = { status: 'passed', passed: true, frames: 300, errors: [], binary_source: 'GODOT_BIN' };
  p.forge.verification.summary.warned_files = 0;
  assert.equal(R.playtestVerdict(p, 'auto').label, 'PLAYABLE');
  assert.deepEqual(R.operatorVerdict(p, REQ), { verdict: 'ship', reasons: [] });
});

test('playtest off and missing reports are labelled honestly', () => {
  const p = clone(run);
  delete p.playtest;
  assert.equal(R.playtestVerdict(p, 'off').label, 'STATIC ONLY');
  assert.equal(R.playtestVerdict(p).state, 'unknown');
});

test('verification summary reads the real verify loop', () => {
  const v = R.verificationSummary(run);
  assert.equal(v.accepted, true);
  assert.equal(v.threshold, 0.7);
  assert.deepEqual(v.files, { checked: 13, passed: 9, warned: 4, failed: 0 });
  assert.deepEqual(v.history, [0.9019]);
  assert.equal(v.stoppedReason, 'accepted');
  assert.equal(v.weakestPath, 'scripts/autoloads/game_state.gd');
  for (let i = 1; i < v.worstFiles.length; i += 1) assert.ok(v.worstFiles[i - 1].score <= v.worstFiles[i].score);
});

test('rejected verification and invalid ledger block', () => {
  const p = clone(run);
  p.forge.verification.accepted = false;
  p.forge.verification.reason = 'below_threshold';
  p.ledger.valid = false;
  const v = R.operatorVerdict(p, REQ);
  assert.equal(v.verdict, 'blocked');
  assert.ok(v.reasons.some((r) => /Verification rejected \(below_threshold, score 0.90\)/.test(r.text)));
  assert.ok(v.reasons.some((r) => /ledger/.test(r.text)));
});

test('repair summary distinguishes applied and proposed actions', () => {
  assert.equal(R.repairSummary(run).clean, true);
  const p = clone(run);
  p.forge.repair = {
    mode: 'suggest',
    actions: [
      { path: 'scripts/a.gd', class: 'syntax', applied: 0 },
      { path: 'scripts/b.gd', class: 'syntax', applied: 0 },
      { path: 'scripts/c.gd', class: 'signal', applied: 0 },
    ],
    proposed_paths: ['scripts/a.gd', 'scripts/b.gd', 'scripts/c.gd'],
  };
  const r = R.repairSummary(p);
  assert.equal(r.mode, 'suggest');
  assert.equal(r.proposed, 3);
  assert.equal(r.applied, 0);
  assert.deepEqual(r.byClass, [{ klass: 'syntax', count: 2 }, { klass: 'signal', count: 1 }]);
  assert.ok(R.operatorVerdict(p, REQ).reasons.some((x) => /3 repair\(s\) proposed/.test(x.text)));
});

test('encounters pair ideal and thermal per enemy', () => {
  const pairs = R.encounterPairs(run.sim.encounters);
  assert.equal(pairs.length, 3);
  for (const pair of pairs) {
    assert.equal(typeof pair.ideal, 'number');
    assert.equal(typeof pair.thermal, 'number');
  }
  assert.deepEqual(R.encounterPairs(null), []);
});

test('digest and file grouping for history', () => {
  const d = R.digestRun(run, REQ, 'run', 1000);
  assert.equal(d.verdict, 'review');
  assert.equal(d.fileCount, run.forge.file_count);
  assert.equal(d.playtest, 'unavailable');
  assert.equal(d.at, 1000);
  const di = R.digestRun(intake, { ...REQ, vision: '' }, 'intake', 5);
  assert.equal(di.source, 'intake');
  const groups = R.groupFiles(run.file_names);
  assert.equal(groups[0].folder, '(root)');
  assert.ok(groups[0].files.includes('project.godot'));
  assert.equal(groups.reduce((n, g) => n + g.files.length, 0), run.file_names.length);
});
