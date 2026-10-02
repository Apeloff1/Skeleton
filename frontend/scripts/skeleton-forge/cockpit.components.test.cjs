'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');
const composeFixture = require('./fixtures/compose.json');
const runFixture = require('./fixtures/run.json');

const View = load('src/skeletonForge/components/ForgeCockpitView.tsx').default;
const q = load('src/skeletonForge/questionnaire.ts');
const m = load('src/skeletonForge/cockpitScreen.ts');

const ERAS = [
  { id: 'boomer_shooter', primary_dps: 120, speed: 1.4, ttk: { trash: 0.4, elite: 2, boss: 30 }, philosophy: 'Speed is armour.' },
  { id: 'soulslike', primary_dps: 60, speed: 0.8, ttk: { trash: 3, elite: 12, boss: 180 }, philosophy: 'Learn the pattern.' },
];

function props(tab, extra = {}) {
  const screen = m.initialScreenState(tab);
  return {
    tab,
    onTab: () => {},
    badges: m.tabBadges(screen, { runPhase: 'idle', erasCount: ERAS.length, questionnaireStep: 0, questionnaireSteps: q.STEPS.length }),
    questionnaire: { state: q.INITIAL_STATE, dispatch: () => {}, beats: q.FALLBACK_BEATS, eras: ERAS, generations: [], onForge: () => {} },
    compose: { vision: 'craft gear, survive the storm, stash and save', compose: { result: composeFixture, vision: 'craft gear, survive the storm, stash and save', loading: false, error: null }, editable: true },
    run: { phase: 'done', payload: runFixture, startedAt: 0, finishedAt: 2300 },
    eras: { eras: ERAS, resultEra: 'boomer_shooter' },
    console: { entries: [], onSubmit: () => {} },
    ...extra,
  };
}

test('tab bar: five tabs, one selected, accessible labels with badges', () => {
  const html = render(h(View, props('build')));
  assert.match(html, /role="tablist"/);
  const tabs = attrs(html, 'aria-label').filter((l) => / tab \d of 5/.test(l));
  assert.deepEqual(tabs, [
    'Questionnaire, tab 1 of 5, step 1 of 5',
    'Compose graph, tab 2 of 5',
    'Forge run, tab 3 of 5',
    'Eras, tab 4 of 5, 2 eras',
    'Console, tab 5 of 5',
  ]);
  assert.equal((html.match(/aria-selected="true"/g) || []).length, 1);
  for (const t of m.COCKPIT_TABS) assert.match(html, new RegExp(`data-testid="cockpit-tab-${t}"`));
});

for (const tab of ['build', 'compose', 'run', 'eras', 'console']) {
  test(`renders only the ${tab} panel`, () => {
    const html = render(h(View, props(tab)));
    assert.match(html, new RegExp(`data-testid="cockpit-panel-${tab}"`));
    for (const other of m.COCKPIT_TABS.filter((x) => x !== tab)) {
      assert.doesNotMatch(html, new RegExp(`data-testid="cockpit-panel-${other}"`));
    }
    assert.match(text(html), new RegExp(m.COCKPIT_TAB_HINTS[tab].slice(0, 20).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  });
}

test('run tab shows forge results inside the cockpit', () => {
  const t = text(render(h(View, props('run'))));
  assert.match(t, /Forged in 2s/);
  assert.match(t, /10\/10 stages succeeded/);
});

test('console tab and notice banner', () => {
  const html = render(h(View, props('console', { notice: 'Offline beats in use' })));
  assert.match(html, /data-testid="console-input"/);
  assert.match(html, /data-testid="cockpit-notice"/);
  assert.match(text(html), /Offline beats in use/);
  assert.doesNotMatch(render(h(View, props('console'))), /data-testid="cockpit-notice"/);
});
