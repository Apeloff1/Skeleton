const { test } = require('node:test');
const { assert } = require('./helpers.cjs');
const {
  SCENE_CHAT_HANDOFF_KEY, SCENE_CHAT_MAX_AGE_MS, SCENE_RECIPES,
  suggestedSceneRecipe, prepareSceneChatHandoff,
  readSceneChatHandoff, sceneHandoffItems,
} = require('../../features/Jeeves/sceneHandoff.ts');

const NOW = Date.UTC(2026, 9, 13, 10);
const values = (patch = {}) => ({
  id: 'draft-1',
  createdAt: NOW,
  buildId: 'game-A',
  era: '16bit',
  recipeKey: 'village',
  conversationId: 'conversation-1',
  assistantMessageId: 'assistant-1',
  ...patch,
});

test('scene handoff uses one bounded catalog of the existing ten composer recipes', () => {
  assert.equal(SCENE_RECIPES.length, 10);
  assert.deepEqual(SCENE_RECIPES.map(r => r.key), [
    'forest', 'village', 'squad', 'armory', 'feast',
    'lab', 'garden', 'shrine', 'dungeon', 'treasury',
  ]);
  assert.deepEqual(SCENE_RECIPES.find(r => r.key === 'lab').items, [
    { category: 'robot', count: 4 },
    { category: 'machine', count: 3 },
    { category: 'crate', count: 5 },
    { category: 'turret', count: 2 },
  ]);
  for (const recipe of SCENE_RECIPES) {
    assert.ok(recipe.items.length > 0 && recipe.items.length <= 10);
    assert.ok(recipe.items.every(i => i.count >= 1 && i.count <= 50));
    assert.equal(new Set(recipe.items.map(i => i.category)).size, recipe.items.length);
  }
});

test('natural language recipe suggestion is bounded and never auto-selects competing alternatives', () => {
  assert.equal(suggestedSceneRecipe('Create a walled village with NPCs'), 'village');
  assert.equal(suggestedSceneRecipe('Let us build a dungeon crawl'), 'dungeon');
  assert.equal(suggestedSceneRecipe('Create an enchanted forest and a sacred shrine'), null);
  assert.equal(suggestedSceneRecipe('Repair Python syntax in a script'), null);
  assert.equal(suggestedSceneRecipe('forest '.repeat(10000)), null);
});

test('user-approved draft contains only trusted recipe key, era and source identity, not model prose', () => {
  const approved = prepareSceneChatHandoff(values());
  assert.equal(approved.version, 1);
  assert.equal(approved.buildId, 'game-A');
  const json = JSON.stringify(approved);
  assert.ok(json.length < 500);
  assert.equal(json.includes('scene code'), false);
  assert.equal(SCENE_CHAT_HANDOFF_KEY, '@tutolage/jeeves-scene-handoff:v1');
  const recovered = readSceneChatHandoff(json, 'draft-1', 'game-A', NOW + 3000);
  assert.deepEqual(recovered, approved);
  assert.deepEqual(sceneHandoffItems(recovered), [
    { category: 'house', count: 8 },
    { category: 'npc', count: 6 },
    { category: 'chest', count: 3 },
    { category: 'tree', count: 5 },
  ]);
});

test('expired, future-dated, foreign game, and replay-with-other-id drafts are refused', () => {
  const raw = JSON.stringify(prepareSceneChatHandoff(values()));
  assert.equal(readSceneChatHandoff(raw, 'draft-2', 'game-A', NOW + 1), null);
  assert.equal(readSceneChatHandoff(raw, 'draft-1', 'game-B', NOW + 1), null);
  assert.equal(readSceneChatHandoff(raw, 'draft-1', 'game-A', NOW + SCENE_CHAT_MAX_AGE_MS + 1), null);
  assert.equal(readSceneChatHandoff(raw, 'draft-1', 'game-A', NOW - 60_001), null);
  assert.deepEqual(readSceneChatHandoff(raw, 'draft-1', 'game-A', NOW + SCENE_CHAT_MAX_AGE_MS), prepareSceneChatHandoff(values()));
});

test('unsafe identity, unknown recipe, unsupported era and build injection are rejected', () => {
  for (const patch of [
    { id: 'abc/def' }, { assistantMessageId: '' },
    { conversationId: 'a'.repeat(200) },
    { buildId: '../other-game' }, { buildId: 'space in game' },
    { era: 'future-backdoor' }, { recipeKey: 'execute-shell' },
    { createdAt: NaN }, { createdAt: -10 },
  ]) {
    assert.throws(() => prepareSceneChatHandoff(values(patch)));
  }
});

test('malformed payloads and forged asset arrays cannot change canonical scene recipe quantities', () => {
  for (const raw of ['{', '{}', '[]', null, 'a'.repeat(3000)]) {
    assert.equal(readSceneChatHandoff(raw, 'draft-1', 'game-A', NOW + 1), null);
  }
  const approved = prepareSceneChatHandoff(values());
  const malicious = JSON.stringify({ ...approved, items: [{ category: 'malicious', count: 100000 }] });
  const parsed = readSceneChatHandoff(malicious, 'draft-1', 'game-A', NOW + 1);
  assert.deepEqual(sceneHandoffItems(parsed), sceneHandoffItems(approved));
  assert.ok(!sceneHandoffItems(parsed).some(item => item.category === 'malicious'));
});

test('scene draft form item arrays are independent of canonical recipe catalog', () => {
  const approved = prepareSceneChatHandoff(values());
  const first = sceneHandoffItems(approved);
  first[0].count = 99;
  first.push({ category: 'custom', count: 100 });
  const next = sceneHandoffItems(approved);
  assert.equal(next[0].count, 8);
  assert.equal(next.length, 4);
});
