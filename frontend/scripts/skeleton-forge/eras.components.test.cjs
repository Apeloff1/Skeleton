'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');

const mod = load('src/skeletonForge/components/EraViewer.tsx');
const EraViewer = mod.default;
const ERAS = [
  { id: 'extraction_now', primary_dps: 108, speed: 195, ttk: { trash: 1.1, elite: 4.5, boss: 60 }, philosophy: 'risk_session_value' },
  { id: 'boomer_shooter', primary_dps: 121.8, speed: 320, ttk: { trash: 0.4, elite: 2, boss: 30 }, philosophy: 'flow_mastery' },
  { id: 'cozy_wholesome', primary_dps: 20, speed: 140, ttk: {}, philosophy: 'comfort' },
];

test('renders an accessible card per era, sorted by name, with result/pinned badges', () => {
  const html = render(h(EraViewer, { eras: ERAS, resultEra: 'boomer_shooter~jrpg@0.30', pinnedEra: 'cozy_wholesome', onSelect: () => {} }));
  const cards = attrs(html, 'aria-label').filter((l) => /primary DPS/.test(l) && !l.startsWith('Era details'));
  assert.equal(cards.length, 3);
  assert.match(cards[0], /^Boomer Shooter: Flow Mastery; primary DPS 121.8, move speed 320, trash time-to-kill 0.4s\. last forge result\.$/);
  assert.match(cards[1], /^Cozy Wholesome: .*trash time-to-kill unknown\. pinned\.$/);
  assert.match(text(html), /RESULT/);
  assert.match(text(html), /PINNED/);
  assert.ok(attrs(html, 'aria-label').includes('3 eras shown.'));
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /data-testid="era-card-boomer_shooter"[^>]*tabindex="0"|tabindex="0"[^>]*data-testid="era-card-boomer_shooter"/);
  assert.match(html, /data-testid="era-sort-name"[^>]*tabindex="0"|tabindex="0"[^>]*data-testid="era-sort-name"/);
  assert.match(html, /tabindex="-1"/);
  assert.ok(attrs(html, 'aria-label').includes('Search eras'));
});

test('selected era opens a detail card with TTK breakdown and use-in-forge', () => {
  const html = render(h(EraViewer, { eras: ERAS, selected: 'extraction_now', onSelect: () => {}, onUseInForge: () => {} }));
  const labels = attrs(html, 'aria-label');
  assert.ok(labels.includes('Era details: Extraction Now'));
  assert.ok(labels.includes('Boss time to kill: 60 seconds'));
  assert.match(text(html), /Use in forge/);
  const pinned = render(h(EraViewer, { eras: ERAS, selected: 'extraction_now', pinnedEra: 'extraction_now', onUseInForge: () => {} }));
  assert.match(text(pinned), /Pinned for next forge/);
});

test('error, loading and empty states', () => {
  const err = render(h(EraViewer, { eras: [], error: 'Backend unreachable', onReload: () => {} }));
  assert.match(text(err), /Could not load eras: Backend unreachable/);
  assert.match(err, /data-testid="era-retry"/);
  const loading = render(h(EraViewer, { eras: [], loading: true }));
  assert.ok(attrs(loading, 'aria-label').includes('Loading eras'));
  const empty = render(h(EraViewer, { eras: [] }));
  assert.match(text(empty), /No eras available/);
});

test('era grid and sort keys, and the plan handoff', () => {
  assert.deepEqual(mod.eraCardIntent(0, { key: 'ArrowDown' }, { cols: 1, count: 3 }), { move: 1 });
  assert.deepEqual(mod.eraCardIntent(2, { key: 'ArrowDown' }, { cols: 1, count: 3 }), { move: 0 });
  assert.deepEqual(mod.eraCardIntent(1, { key: 'ArrowDown' }, { cols: 3, count: 3 }), null);
  assert.deepEqual(mod.eraCardIntent(0, { key: 'Escape' }, { cols: 1, count: 3 }), { dismiss: true });
  assert.equal(mod.eraCardIntent(0, { key: 'Enter' }, { cols: 1, count: 3 }), null);
  assert.equal(mod.eraSortIndex(0, { key: 'ArrowRight' }, 4), 1);
  assert.equal(mod.eraSortIndex(3, { key: 'ArrowRight' }, 4), 0);
  assert.equal(mod.eraSortIndex(1, { key: ' ' }, 4), null);
  const html = render(h(EraViewer, { eras: ERAS, onViewPlan: () => {} }));
  assert.match(html, /data-testid="era-view-plan"/);
  assert.doesNotMatch(render(h(EraViewer, { eras: ERAS })), /data-testid="era-view-plan"/);
});

test('responsive columns', () => {
  assert.equal(mod.columnsFor(360), 1);
  assert.equal(mod.columnsFor(700), 2);
  assert.equal(mod.columnsFor(1200), 3);
  const wide = render(h(EraViewer, { eras: ERAS, initialWidth: 1200 }));
  assert.match(wide, /width:32%/);
  const phone = render(h(EraViewer, { eras: ERAS, initialWidth: 360 }));
  assert.match(phone, /width:100%/);
});
