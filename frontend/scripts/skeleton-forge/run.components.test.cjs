'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');
const runFixture = require('./fixtures/run.json');

const Panel = load('src/skeletonForge/components/ForgeRunPanel.tsx').default;

test('idle panel explains what will appear and can open the plan', () => {
  const t = text(render(h(Panel, { phase: 'idle', payload: null })));
  assert.match(t, /No run yet/);
  const linked = render(h(Panel, { phase: 'idle', payload: null, onViewPlan: () => {} }));
  assert.match(linked, /data-testid="run-view-plan"/);
});

test('running panel shows elapsed clock, queued stages and cancel', () => {
  const html = render(h(Panel, { phase: 'running', payload: null, startedAt: 1000, now: 13500, onCancel: () => {} }));
  const t = text(html);
  assert.match(t, /Forging… 12s/);
  assert.match(t, /results land together/);
  const stages = attrs(html, 'aria-label').filter((l) => l.startsWith('Stage '));
  assert.equal(stages.length, 10);
  assert.ok(stages.every((l) => l.endsWith(': queued')));
  assert.match(html, /data-testid="run-cancel"/);
  assert.match(html, /aria-busy="true"/);
  assert.match(html, /data-testid="stage-ingest"[^>]*tabindex="0"|tabindex="0"[^>]*data-testid="stage-ingest"/);
  const quiet = render(h(Panel, { phase: 'running', payload: null, startedAt: 1000, now: 13500, reduceMotion: true }));
  assert.ok(!attrs(quiet, 'aria-label').includes('Forge running'));
  assert.match(text(quiet), /Forging… 12s/);
  assert.doesNotMatch(html, /data-testid="run-result"/);
});

test('done panel: stage track, era, blueprint, verify and repair', () => {
  const html = render(h(Panel, { phase: 'done', payload: runFixture, startedAt: 0, finishedAt: 2300, onViewEra: () => {}, onViewPlan: () => {}, onRetry: () => {} }));
  const t = text(html);
  const labels = attrs(html, 'aria-label');
  assert.match(t, /Forged in 2s/);
  assert.match(t, /10\/10 stages succeeded/);
  assert.ok(labels.some((l) => /^Stage 6, Forge, verify & repair: succeeded, \d+ milliseconds$/.test(l)));
  assert.match(t, /RESULTING ERA Boomer Shooter/);
  assert.ok(labels.includes(`Blueprint: ${runFixture.forge.blueprint_id}`));
  assert.ok(labels.includes('Files: 24'));
  assert.ok(labels.includes('Ledger: valid'));
  assert.ok(labels.includes('Verified'));
  assert.ok(labels.some((l) => l.startsWith('Verification score 90%, accept at 70%')));
  assert.ok(labels.includes('No repair needed'));
  assert.ok(labels.includes('Headless playtest off'));
  assert.ok(labels.includes('Composed systems: crafting, collapse, extraction, companion'));
  assert.match(html, /data-testid="run-view-era"/);
  assert.match(html, /data-testid="run-view-plan"/);
  assert.match(t, /Jeeves/);
});

test('failed run: error banner, failed stage, repair unresolved, score history', () => {
  const p = JSON.parse(JSON.stringify(runFixture));
  p.succeeded = false;
  p.run.stages[5] = { name: 'forge', status: 'FAILED', duration_s: 0.5, error: 'verify exhausted' };
  p.forge.verify_loop = { accepted: false, threshold: 0.7, trace: { rounds: 3, history: [0.41, 0.52, 0.66] } };
  p.forge.verification = { accepted: false, score: 0.66, blocking_issues: ['x'] };
  p.forge.repair = { strategy: 'regen' };
  const html = render(h(Panel, { phase: 'done', payload: p, startedAt: 0, finishedAt: 1000 }));
  const labels = attrs(html, 'aria-label');
  assert.ok(labels.includes('Run finished with failures'));
  assert.ok(labels.some((l) => l.startsWith('Stage 6, Forge, verify & repair: failed') && l.endsWith('error verify exhausted')));
  assert.ok(labels.includes('Verification failed'));
  assert.ok(labels.includes('Repair attempted, still failing'));
  assert.ok(labels.includes('Score by round: 41%, 52%, 66%'));
  assert.ok(labels.includes('Blocking: 1'));

  const err = render(h(Panel, { phase: 'error', payload: null, error: 'unknown archetype', startedAt: 0, finishedAt: 10, onRetry: () => {} }));
  assert.match(text(err), /unknown archetype/);
  assert.match(err, /role="alert"/);
  assert.match(err, /data-testid="run-retry"/);
  const errPlan = render(h(Panel, { phase: 'error', payload: null, error: 'unknown archetype', onViewPlan: () => {} }));
  assert.match(errPlan, /data-testid="run-view-plan"/);
});

test('stage keys walk the pipeline as a single column', () => {
  const mod = load('src/skeletonForge/components/ForgeRunPanel.tsx');
  assert.equal(mod.stageKeyTarget(0, { key: 'ArrowDown' }, 10), 1);
  assert.equal(mod.stageKeyTarget(3, { key: 'End' }, 10), 9);
  assert.equal(mod.stageKeyTarget(3, { key: 'Home' }, 10), 0);
  assert.equal(mod.stageKeyTarget(9, { key: 'ArrowDown' }, 10), null);
  assert.equal(mod.stageKeyTarget(1, { key: 'Enter' }, 10), null);
});

test('reduced-motion press feedback drops the scale', () => {
  const theme = load('src/skeletonForge/components/theme.ts');
  assert.deepEqual(theme.pressFeedback(false, false), null);
  assert.deepEqual(theme.pressFeedback(true, true), { opacity: 0.85 });
  const full = theme.pressFeedback(true, false);
  assert.equal(full.opacity, 0.75);
  assert.deepEqual(full.transform, [{ scale: 0.98 }]);
});
