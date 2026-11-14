'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const R = load('src/features/GalaxyStudioFactory/genreRegistry.ts');
const G = load('src/skeletonForge/galaxyGenres.ts');
const F = load('src/features/GalaxyStudioFactory/fallbackGenres.ts');
const C = load('src/skeletonForge/genreCatalog.ts');
test('69 distinct historical offline choices survive recovery without duplicates', () => {
  const offline = R.mergeGalaxyGenreCatalog(null);
  assert.equal(R.GALAXY_OFFLINE_COUNT, 69);
  assert.equal(offline.length, 69);
  assert.equal(new Set(offline.map(x => x.id)).size, 69);
  assert.equal(G.GALAXY_CHOICES.length, 69);
  assert.equal(G.mappedBriefGenre('beat_em_up'), 'beat-em-up');
  assert.equal(G.mappedBriefGenre('shoot_em_up'), 'shoot-em-up');
});
test('truncated live server catalog cannot erase historical entries', () => {
  const joined = R.mergeGalaxyGenreCatalog({ genres: [
    { id: 'rpg', name: 'Updated RPG', subgenres: ['heroes'] },
    { id: 'shoot_em_up', name: 'Updated Shooter', subgenres: ['waves'] },
    { id: '../../bad', name: 'hijack' },
    { id: 'rpg', name: 'Updated RPG', subgenres: ['heroes'] },
  ] });
  assert.equal(joined.length, 69);
  assert.equal(joined.find(x => x.id === 'rpg').name, 'Updated RPG');
  assert.equal(joined.find(x => x.id === 'shoot_em_up').name, 'Updated Shooter');
  assert.ok(joined.some(x => x.id === 'metaverse_social'));
  assert.ok(!joined.some(x => x.id === '../../bad'));
});
test('unsafe unknown live records are excluded without losing offline catalog', () => {
  const bad = { genres: [{ id: '__proto__', name: 'invalid' }, { id: 'xy', subgenres: [NaN, null] }] };
  const items = R.mergeGalaxyGenreCatalog(bad);
  assert.ok(!items.some(x => x.id === '__proto__'));
  assert.ok(items.find(x => x.id === 'xy'));
  assert.ok(items.some(x => x.id === 'beat_em_up'));
});

test('historical metadata and ordering survive duplicate recoveries', () => {
  const offline = R.mergeGalaxyGenreCatalog(null);
  const original = F.FALLBACK_GENRES;
  assert.deepEqual(offline.slice(0, original.length), original);
  assert.equal(new Set(G.GALAXY_CHOICES.map(x => x.id)).size, 69);
  assert.equal(C.GENRE_COUNT, 158);
  for (const entry of offline) {
    assert.ok(C.GENRE_CHOICES.includes(G.mappedBriefGenre(entry.id)), entry.id);
    assert.equal(G.galaxyGenre(entry.id).name, entry.name);
  }
  const fallbackWithoutRecovered = original.filter(x => !R.RECOVERED_GENRES.some(y => y.id === x.id));
  const rebuilt = R.mergeOfflineGalaxyGenres(fallbackWithoutRecovered, R.RECOVERED_GENRES);
  assert.equal(rebuilt.length, 69);
  assert.equal(new Set(rebuilt.map(x => x.id)).size, 69);
});
