'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const fixture = require('./fixtures/eras.json');

const E = load('src/forgeOperator/eraSummary.ts');
const eras = fixture.eras;
const clone = (x) => JSON.parse(JSON.stringify(x));

test('summarizeEra returns null for null/undefined/empty id', () => {
  assert.equal(E.summarizeEra(null), null);
  assert.equal(E.summarizeEra(undefined), null);
  assert.equal(E.summarizeEra({}), null);
  assert.equal(E.summarizeEra({ id: '' }), null);
});

test('summarizeEra flattens extraction_now fixture', () => {
  const row = eras.find((e) => e.id === 'extraction_now');
  const s = E.summarizeEra(row);
  assert.equal(s.id, 'extraction_now');
  assert.equal(s.philosophy, 'risk_session_value');
  assert.equal(s.philosophyLabel, 'risk session value');
  assert.equal(s.statsLabel, 'DPS 108 · speed 195');
  assert.equal(s.ttkLabel, 'trash 1.1s · elite 4.5s · boss 60s · glass 1.8s');
  assert.equal(s.dps, 108);
  assert.equal(s.speed, 195);
});

test('formatTtk omits missing keys and empty → em dash', () => {
  assert.equal(E.formatTtk(null), '—');
  assert.equal(E.formatTtk(undefined), '—');
  assert.equal(E.formatTtk({}), '—');
  assert.equal(E.formatTtk({ trash: 1.1, elite: 4.5 }), 'trash 1.1s · elite 4.5s');
  assert.equal(E.formatTtk({ player_glass: 0.4 }), 'glass 0.4s');
  assert.equal(E.formatTtk({ boss: 60 }), 'boss 60s');
});

test('formatEraStats and humanizePhilosophy', () => {
  assert.equal(E.formatEraStats(null), '—');
  assert.equal(E.formatEraStats({ id: 'x', primary_dps: 108, speed: 195 }), 'DPS 108 · speed 195');
  assert.equal(E.formatEraStats({ id: 'x', primary_dps: 85.8, speed: 155 }), 'DPS 85.8 · speed 155');
  assert.equal(E.humanizePhilosophy('risk_session_value'), 'risk session value');
  assert.equal(E.humanizePhilosophy('presence'), 'presence');
  assert.equal(E.humanizePhilosophy(null), '');
  assert.equal(E.humanizePhilosophy(''), '');
});

test('listPhilosophies returns sorted unique', () => {
  assert.deepEqual(E.listPhilosophies(null), []);
  assert.deepEqual(E.listPhilosophies([]), []);
  const phils = E.listPhilosophies(eras);
  assert.equal(phils.length, eras.length, 'fixture eras each have unique philosophy');
  assert.deepEqual(phils, [...phils].sort((a, b) => a.localeCompare(b)));
  assert.ok(phils.includes('risk_session_value'));
  assert.ok(phils.includes('loss_forward'));
});

test('filterEras by query and philosophy', () => {
  assert.equal(E.filterEras(null).length, 0);
  assert.equal(E.filterEras(eras, null).length, eras.length);
  assert.equal(E.filterEras(eras, {}).length, eras.length);

  const soul = E.filterEras(eras, { query: 'SOUL' });
  assert.equal(soul.length, 1);
  assert.equal(soul[0].id, 'soulslike');

  const phil = E.filterEras(eras, { philosophy: 'Score_Attack' });
  assert.equal(phil.length, 1);
  assert.equal(phil[0].id, 'arcade_golden_age');

  const both = E.filterEras(eras, { query: 'arcade', philosophy: 'score_attack' });
  assert.equal(both.length, 1);

  const miss = E.filterEras(eras, { query: 'arcade', philosophy: 'loss_forward' });
  assert.equal(miss.length, 0);
});

test('summarizeErasCatalog count / fastest / glassiest', () => {
  const empty = E.summarizeErasCatalog([]);
  assert.equal(empty.count, 0);
  assert.deepEqual(empty.philosophies, []);
  assert.equal(empty.fastestId, null);
  assert.equal(empty.glassiestId, null);

  const cat = E.summarizeErasCatalog(eras);
  assert.equal(cat.count, 24);
  assert.equal(cat.count, fixture.count);
  assert.equal(cat.fastestId, 'fighting_game'); // speed 240
  assert.equal(cat.glassiestId, 'arcade_golden_age'); // player_glass 0.4
  assert.ok(cat.philosophies.includes('frame_truth'));
  assert.equal(cat.philosophies.length, 24);
});

test('summarizeErasCatalog ties keep first occurrence', () => {
  const a = { id: 'a', primary_dps: 1, speed: 10, ttk: { player_glass: 2 }, philosophy: 'p1' };
  const b = { id: 'b', primary_dps: 1, speed: 10, ttk: { player_glass: 2 }, philosophy: 'p2' };
  const cat = E.summarizeErasCatalog([a, b]);
  assert.equal(cat.fastestId, 'a');
  assert.equal(cat.glassiestId, 'a');
});

test('operatorTabs still lists eras', () => {
  const T = load('src/forgeOperator/operatorTabs.ts');
  assert.ok(T.OPERATOR_TABS.includes('eras'));
  assert.equal(T.OPERATOR_TAB_LABELS.eras, 'Eras');
  assert.equal(T.parseOperatorTab('eras'), 'eras');
});
