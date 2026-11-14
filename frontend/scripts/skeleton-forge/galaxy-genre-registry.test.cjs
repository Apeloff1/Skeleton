'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { load } = require('./harness.cjs');
const Registry = load('src/features/GalaxyStudioFactory/genreRegistry.ts');
const { FALLBACK_GENRES } = load('src/features/GalaxyStudioFactory/fallbackGenres.ts');
const H = load('src/skeletonForge/creatorBridge.ts');

function ids(rows) { return rows.map(row => row.id); }
function remote(id, extra = {}) {
  return {
    id, name: 'Live ' + id, icon: '🎮', color: '#ABCDEF',
    desc: 'Bounded online description', screens: 8, components: 9,
    logic_files: 5, subgenres: ['precision_platformer', 'roguelite'],
    subgenre_count: 2, ...extra,
  };
}

test('offline fallback retains all 69 entries on empty, malformed or truncated live catalog', () => {
  assert.equal(FALLBACK_GENRES.length, 69);
  const fallbackIds = ids(FALLBACK_GENRES);
  for (const value of [null, {}, { genres: 'invalid' }, { genres: [] },
    { genres: [remote('fps', { name: 'Updated FPS' })] }]) {
    const merged = Registry.mergeGalaxyGenreCatalog(value);
    assert.deepEqual(ids(merged).slice(0, 69), fallbackIds);
    assert.equal(new Set(ids(merged)).size, merged.length);
  }
});

test('live valid rows enrich old records without reordering or hiding historical choices', () => {
  const input = {
    genres: [
      remote('fps', { name: 'Extended FPS', color: '#0000ff',
        subgenres: ['survival_fps', 'survival_fps', 'arena_shooter'] }),
      remote('precision_platformer', { name: 'Precision Platformer' }),
    ],
  };
  const result = Registry.mergeGalaxyGenreCatalog(input);
  assert.equal(result.length, 70);
  assert.equal(result[3].id, FALLBACK_GENRES[3].id);
  assert.equal(result.find(x => x.id === 'fps').name, 'Extended FPS');
  assert.deepEqual(result.find(x => x.id === 'fps').subgenres, ['survival_fps', 'arena_shooter']);
  assert.equal(result.at(-1).id, 'precision_platformer');
  assert.equal(Registry.recoveredGalaxyGenre(result, 'precision_platformer').name, 'Precision Platformer');
  assert.equal(Registry.recoveredGalaxyGenre(FALLBACK_GENRES, 'precision_platformer'), null);
  const bridge = H.handoffFromGalaxy({
    title: 'A precision parkour game', vision: '', genreId: 'precision_platformer',
  }, null, 1700000000000);
  assert.equal(bridge.brief.genre, 'precision-platformer');
});

test('untrusted live rows cannot introduce malformed object graphs or unbounded labels', () => {
  const junk = [
    null, 42, 'fps', [], remote('__proto__'), remote('has spaces'),
    remote('bad/id'), remote('too_long_' + 'x'.repeat(90)),
    remote('fps', {
      name: 'x'.repeat(1000), desc: 'y'.repeat(10000),
      color: 'javascript:alert(1)', screens: Infinity, components: -2,
      subgenres: [12, '__proto__', 'a valid? id', 'valid_new', 'valid_new', ...Array(400).fill('some_genre')],
    }),
    remote('new_genre', { name: '', subgenres: 'bad', logic_files: 100000 }),
  ];
  const merged = Registry.mergeGalaxyGenreCatalog({ genres: junk });
  assert.equal(merged.length, 70);
  const fps = merged.find(x => x.id === 'fps');
  const fallback = FALLBACK_GENRES.find(x => x.id === 'fps');
  assert.equal(fps.name, fallback.name);
  assert.equal(fps.desc, fallback.desc);
  assert.equal(fps.color, fallback.color);
  assert.equal(fps.screens, fallback.screens);
  assert.equal(fps.components, fallback.components);
  assert.equal(fps.subgenres[0], 'valid_new');
  assert.equal(fps.subgenres.filter(x => x === 'some_genre').length, 1);
  assert.ok(fps.subgenres.length <= Registry.GALAXY_SUBGENRE_LIMIT);
  assert.equal(merged.at(-1).id, 'new_genre');
  assert.equal(merged.at(-1).logic_files, 0);
  assert.equal(Registry.recoveredGalaxyGenre(merged, 'bad/id'), null);
});

test('bounded deduplication under a large live response preserves every historical genre', () => {
  const rows = Array.from({ length: 1600 }, (_, i) => remote('live_' + i));
  const out = Registry.mergeGalaxyGenreCatalog({ genres: rows });
  assert.equal(out.length, 69 + Registry.GALAXY_LIVE_GENRE_LIMIT);
  assert.ok(out.some(x => x.id === 'live_511'));
  assert.ok(!out.some(x => x.id === 'live_512'));
  assert.ok(FALLBACK_GENRES.every(g => out.some(x => x.id === g.id)));
});

test('Galaxy UI merges validated live genres and never silently overwrites a manual selection', () => {
  const file = path.resolve(__dirname, '../../src/features/GalaxyStudioFactory/GalaxyStudioFactoryModal.tsx');
  const source = fs.readFileSync(file, 'utf8');
  assert.match(source, /setGenres\(mergeGalaxyGenreCatalog\(data\)\)/);
  assert.match(source, /recoveredGalaxyGenre\(genres, id\)/);
  assert.match(source, /pendingGenreRestore\.current = null; setSelectedGenre\(g\)/);
  assert.match(source, /pendingGenreRestore\.current = null; setSelectedGenre\(null\)/);
});
