'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const G = load('src/skeletonForge/galaxyHandoff.ts');
const S = load('src/skeletonForge/galaxyProfileSnapshot.ts');

function sample() {
  const payload = {
    title: 'Nebula Forge', genre: 'beat_em_up', game_vision: 'An original arcade brawler',
    narrative_phases: { prelude: { count: 1 } }, extra_params: { quest_variety: 98 },
    style_params: { graphic_style: 'pixel_art' },
  };
  for (const field of G.MATRIX_FIELDS) payload[field] = { kickoff: { count: 2 } };
  return payload;
}

test('complete matrices and extra controls survive persistent profile round-trip', () => {
  const source = sample(), saved = S.makeSavedGalaxyProfile(source, 100_000);
  source.extra_params.quest_variety = 0;
  const restored = S.parseSavedGalaxyProfile(JSON.parse(JSON.stringify(saved)), 110_000);
  assert.equal(restored.profile.config.extra_params.quest_variety, 98);
  assert.equal(G.MATRIX_FIELDS.filter(field => restored.profile.config[field]).length, 14);
  assert.equal(restored.profile.config.genre, 'beat_em_up');
});
test('saved authoring expires, refuses clock reversal and invalid content', () => {
  const saved = S.makeSavedGalaxyProfile(sample(), 100_000);
  assert.equal(S.parseSavedGalaxyProfile(saved, 100_000 + S.SAVED_GALAXY_TTL_MS + 1), null);
  assert.equal(S.parseSavedGalaxyProfile(saved, 50_000), null);
  assert.equal(S.parseSavedGalaxyProfile({ ...saved, unknown: true }, 110_000), null);
  assert.equal(S.parseSavedGalaxyProfile({ ...saved, profile: { ...saved.profile, config: {} } }, 110_000), null);
});
test('saved authoring never loosens finite-number budget', () => {
  const source = sample();
  source.extra_params.quest_variety = NaN;
  assert.throws(() => S.makeSavedGalaxyProfile(source), /transfer rejected/);
});
