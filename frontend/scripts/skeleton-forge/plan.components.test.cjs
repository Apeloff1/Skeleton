'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');
const runFixture = require('./fixtures/run.json');

const mod = load('src/skeletonForge/components/PlanViewer.tsx');
const PlanViewer = mod.default;
const ERAS = [
  { id: 'boomer_shooter', primary_dps: 121.8, speed: 320, ttk: { trash: 0.4, elite: 2, boss: 30 }, philosophy: 'movement_gun_poetry' },
];

function tagHas(html, testId, attr) {
  const re = new RegExp(`<[^>]*(?:data-testid="${testId}"[^>]*${attr}|${attr}[^>]*data-testid="${testId}")[^>]*>`);
  return re.test(html);
}

test('empty and error states name the way back', () => {
  const empty = render(h(PlanViewer, { payload: null, onBack: () => {} }));
  assert.match(text(empty), /No plan yet/);
  assert.match(empty, /data-testid="plan-back"/);
  assert.ok(attrs(empty, 'aria-label').includes('No plan yet'));
  const err = render(h(PlanViewer, { payload: null, error: 'Backend unreachable' }));
  assert.match(text(err), /Backend unreachable/);
  assert.match(err, /role="alert"/);
});

test('drafting state keeps its label and drops the spinner when motion is reduced', () => {
  const spinning = render(h(PlanViewer, { payload: null, running: true }));
  assert.ok(attrs(spinning, 'aria-label').includes('Drafting the plan'));
  assert.match(text(spinning), /Jeeves is drafting the plan/);
  const quiet = render(h(PlanViewer, { payload: null, running: true, reduceMotion: true }));
  assert.ok(!attrs(quiet, 'aria-label').includes('Drafting the plan'));
  assert.match(text(quiet), /Jeeves is drafting the plan/);
});

test('fixture plan: slack unknown, one mix tab stop, era and run actions', () => {
  const html = render(h(PlanViewer, {
    payload: runFixture, eras: ERAS, pinnedEra: 'boomer_shooter',
    onViewEra: () => {}, onViewRun: () => {}, onBack: () => {},
  }));
  const labels = attrs(html, 'aria-label');
  assert.ok(labels.some((l) => l.startsWith('Build plan for Boomer Shooter') && l.includes('Slack unknown.')));
  assert.ok(labels.includes('Slack: unknown'));
  assert.match(text(html), /Honours the pinned era/);
  assert.match(text(html), /Mix fits the thermal budget/);
  assert.ok(tagHas(html, 'plan-mix-trash', 'tabindex="0"'));
  assert.ok(tagHas(html, 'plan-mix-elite', 'tabindex="-1"'));
  assert.ok(tagHas(html, 'plan-mix-boss', 'tabindex="-1"'));
  assert.match(html, /data-testid="plan-open-era"/);
  assert.match(html, /data-testid="plan-open-run"/);
});

test('learned notes and a measured slack render in the plan', () => {
  const payload = {
    ...runFixture,
    build_plan: {
      ...runFixture.build_plan,
      adapt: 'hold',
      slack: 0.42,
      notes: [...runFixture.build_plan.notes, 'imported mix — no search', 'moe bias=heat'],
    },
  };
  const t = text(render(h(PlanViewer, { payload, eras: ERAS })));
  assert.match(t, /42%/);
  assert.match(t, /Imported/);
  assert.match(t, /Mixture of experts/);
  assert.doesNotMatch(t, /Slack is unknown/);
});

test('mix keys move a single column and ignore activation', () => {
  assert.equal(mod.planMixKey(0, { key: 'ArrowDown' }, 3), 1);
  assert.equal(mod.planMixKey(0, { key: 'End' }, 3), 2);
  assert.equal(mod.planMixKey(2, { key: 'ArrowDown' }, 3), null);
  assert.equal(mod.planMixKey(1, { key: 'Enter' }, 3), null);
});
