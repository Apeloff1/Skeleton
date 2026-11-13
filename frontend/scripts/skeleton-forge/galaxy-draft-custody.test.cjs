'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { load } = require('./harness.cjs');

const Draft = load('src/features/GalaxyStudioFactory/galaxyDraftCodec.ts');
const matrices = [
  'mechanics', 'world', 'art', 'audio', 'tech', 'monetisation', 'qa', 'agent',
  'vector_db', 'plagiarism', 'rdbms', 'styles', 'mutation', 'unique_flair',
];
const NOW = 1700000000000;
function source() {
  return {
    schema: Draft.GALAXY_DRAFT_SCHEMA, savedMs: NOW,
    title: 'Expedition 20', gameVision: 'A moon-base game with original progression',
    systemArch: 'Offline-first deterministic quests',
    worldLaws: 'No arbitrary code execution',
    agentInstructions: 'Local Jeeves advisor',
    genreId: 'rpg', subgenreId: 'action_rpg',
    extraGenreIds: ['puzzle', 'survival'], extraSubgenreIds: ['mystery_vn'],
    multiGenreMode: true, quickMode: false,
    complexity: 9, ageTarget: 'ALL', selectedEraId: 'ps5_2020',
    ageEraYear: 2026, targetFiles: 250_000,
    scaleCommand: '250,000 files', showDescriptions: false,
    classic: { worldSize: 8, aiComplexity: 9, physicsRealism: 7, juice: 5 },
    styleChoices: { animationStyle: 'cinematic', cameraEffects: false, gamePace: 'breakneck' },
    styleParams: { graphic_style: 'pixel_art', music_style: 'synthwave' },
    extraParams: Object.fromEntries(Array.from({ length: 100 }, (_, i) => ['param_' + i, i % 11])),
    production: {
      sliders: { detail: 83, accessibility: 97 },
      platforms: ['android', 'ios', 'steam'],
      languages: ['en', 'no'],
      monetization: 'premium',
      saveSystem: 'auto_continuous', networkMode: 'offline_only',
      artDirection: 'stylized', gameTone: 'heroic',
      narrativeStructure: 'branching', perspective: 'third_person_close',
    },
    matrices: Object.fromEntries(matrices.map((name, i) => [
      name, { ['phase_' + i]: { complexity: i * 10, intricacy: i * 7, diversity: 1000 } },
    ])),
    narrative: { prologue: { count: 2, complexity: 90, secrets: 43 }, epilogue: { count: 1 } },
  };
}

test('all 14 Galaxy matrix families, narrative phases, and 100 extended controls survive custody', () => {
  const snapshot = Draft.normalizeGalaxyDraft(source(), NOW);
  assert.ok(snapshot);
  assert.equal(Object.keys(snapshot.matrices).length, 14);
  assert.deepEqual(new Set(Object.keys(snapshot.matrices)), new Set(matrices));
  assert.equal(Object.keys(snapshot.extraParams).length, 100);
  for (const family of matrices) {
    assert.equal(Object.keys(snapshot.matrices[family]).length, 1);
  }
  assert.equal(snapshot.matrices.unique_flair.phase_13.diversity, 1000);
  assert.equal(snapshot.narrative.prologue.secrets, 43);
  assert.equal(snapshot.classic.worldSize, 8);
  assert.equal(snapshot.targetFiles, 250_000);
  assert.equal(snapshot.scaleCommand, '250,000 files');
  assert.equal(snapshot.showDescriptions, false);
  assert.equal(snapshot.production.sliders.accessibility, 97);
  assert.equal(snapshot.styleChoices.animationStyle, 'cinematic');
  assert.equal(snapshot.styleChoices.cameraEffects, false);
  assert.equal(snapshot.extraGenreIds.length, 2);
});

test('draft cannot restore after expiry or from an invalid / future timestamp', () => {
  const original = source();
  assert.equal(Draft.normalizeGalaxyDraft(original, NOW + Draft.GALAXY_DRAFT_TTL_MS + 1), null);
  assert.equal(Draft.normalizeGalaxyDraft(original, NOW - 30_001), null);
  assert.equal(Draft.normalizeGalaxyDraft({ ...original, savedMs: 'today' }, NOW), null);
  assert.equal(Draft.normalizeGalaxyDraft({ ...original, schema: 'another.schema' }, NOW), null);
});

test('unsafe and unknown matrix families, ranges and option enum values fail closed', () => {
  const original = source();
  original.matrices.invalid = { q: { x: 999 } };
  original.matrices.mechanics.constructor = { x: 999 };
  original.matrices.mechanics.phase_0.nan = Number.NaN;
  original.matrices.mechanics.phase_0.negative = -1;
  original.matrices.mechanics.phase_0.too_large = 1001;
  original.styleChoices.animationStyle = 'remote_code_exec';
  original.styleChoices.cameraEffects = 'true';
  original.styleChoices.unknown = 'x';
  original.classic.worldSize = Number.POSITIVE_INFINITY;
  original.extraParams.param_1 = -3;
  original.production.sliders.detail = 110;
  original.targetFiles = 2_000_000;
  original.scaleCommand = 'x'.repeat(500);
  const result = Draft.normalizeGalaxyDraft(original, NOW);
  assert.ok(result);
  assert.equal(result.matrices.invalid, undefined);
  assert.equal(Object.hasOwn(result.matrices.mechanics, 'constructor'), false);
  assert.deepEqual(result.matrices.mechanics.phase_0, { complexity: 0, intricacy: 0, diversity: 1000 });
  assert.equal(result.styleChoices.animationStyle, undefined);
  assert.equal(result.styleChoices.cameraEffects, undefined);
  assert.equal(result.styleChoices.unknown, undefined);
  assert.equal(result.classic.worldSize, undefined);
  assert.equal(result.extraParams.param_1, undefined);
  assert.equal(result.production.sliders.detail, undefined);
  assert.equal(result.targetFiles, 1_000_000);
  assert.equal(result.scaleCommand.length, 120);
});

test('Galaxy studio button snapshots draft before invoking the separate Forge handoff', () => {
  const root = path.resolve(__dirname, '../..');
  const modal = fs.readFileSync(path.join(root, 'src/features/GalaxyStudioFactory/GalaxyStudioFactoryModal.tsx'), 'utf8');
  const route = fs.readFileSync(path.join(root, 'app/galaxy.tsx'), 'utf8');
  assert.match(modal, /await saveGalaxyDraft\(snapshot\)/);
  assert.match(modal, /matrices: matrixValues, narrative: narrativePhaseValues/);
  assert.match(modal, /disabled=\{handoffBusy\}/);
  assert.match(modal, /onRequestClose=\{\(\) => \{ void persistAndClose\(\); \}\}/);
  assert.match(modal, /await persistGalaxyDraft\(\);/);
  assert.match(modal, /targetFiles, scaleCommand, showDescriptions/);
  assert.match(modal, /onSendToForge\(\{ title, vision: gameVision/);
  assert.match(route, /loadGalaxyDraft\(\)/);
  assert.match(route, /initialGalaxyDraft=\{savedGalaxy\}/);
});
