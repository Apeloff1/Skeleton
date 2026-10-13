/** Reviewed Jeeves -> Scene Composer handoff.
 *
 * Untrusted chat text never becomes a forge command. The handoff records only
 * a known editor recipe, a canonical project ID, an era and bounded provenance.
 * The Scene Composer requires a matching deep-link identity and then loads a
 * local form draft. Actual scene creation stays behind its existing user action.
 */
import { validProjectId } from '../../src/product/worldWorkspace';

export const SCENE_CHAT_HANDOFF_KEY = '@tutolage/jeeves-scene-handoff:v1';
export const SCENE_CHAT_MAX_AGE_MS = 60 * 60 * 1000;
export const SCENE_ERAS = ['8bit', '16bit', 'modern', 'nextgen'] as const;

export const SCENE_RECIPES = [
  { key: 'forest', icon: '🌲', name: 'Enchanted Forest', items: [
    { category: 'tree', count: 12 }, { category: 'critter', count: 5 },
    { category: 'boulder', count: 4 }, { category: 'plant', count: 6 },
  ] },
  { key: 'village', icon: '🏘️', name: 'Walled Village', items: [
    { category: 'house', count: 8 }, { category: 'npc', count: 6 },
    { category: 'chest', count: 3 }, { category: 'tree', count: 5 },
  ] },
  { key: 'squad', icon: '🛡️', name: 'Hero Squad', items: [
    { category: 'character', count: 4 }, { category: 'sword', count: 4 },
    { category: 'potion', count: 3 },
  ] },
  { key: 'armory', icon: '⚔️', name: 'Armory', items: [
    { category: 'sword', count: 5 }, { category: 'axe', count: 3 },
    { category: 'bow', count: 3 }, { category: 'chest', count: 4 },
  ] },
  { key: 'feast', icon: '🍞', name: 'Tavern Feast', items: [
    { category: 'table', count: 3 }, { category: 'bread', count: 4 },
    { category: 'cake', count: 2 }, { category: 'barrel', count: 4 },
  ] },
  { key: 'lab', icon: '🤖', name: 'Robotics Lab', items: [
    { category: 'robot', count: 4 }, { category: 'machine', count: 3 },
    { category: 'crate', count: 5 }, { category: 'turret', count: 2 },
  ] },
  { key: 'garden', icon: '🌸', name: 'Botanical Garden', items: [
    { category: 'tree', count: 6 }, { category: 'rose_bush', count: 5 },
    { category: 'sunflower', count: 5 }, { category: 'mushroom', count: 4 },
    { category: 'fountain', count: 1 },
  ] },
  { key: 'shrine', icon: '⛩️', name: 'Sacred Shrine', items: [
    { category: 'shrine', count: 2 }, { category: 'altar', count: 1 },
    { category: 'obelisk', count: 2 }, { category: 'torch', count: 4 },
    { category: 'banner', count: 4 },
  ] },
  { key: 'dungeon', icon: '🗝️', name: 'Dungeon Crawl', items: [
    { category: 'chest', count: 4 }, { category: 'spike_trap', count: 4 },
    { category: 'bat', count: 4 }, { category: 'torch', count: 5 },
    { category: 'door', count: 3 },
  ] },
  { key: 'treasury', icon: '💎', name: 'Royal Treasury', items: [
    { category: 'gold_coin', count: 6 }, { category: 'diamond', count: 4 },
    { category: 'chest', count: 4 }, { category: 'medallion', count: 4 },
  ] },
] as const;

export type SceneEra = typeof SCENE_ERAS[number];
export type SceneRecipeKey = typeof SCENE_RECIPES[number]['key'];

export type SceneChatHandoff = {
  version: 1;
  id: string;
  createdAt: number;
  buildId: string;
  era: SceneEra;
  recipeKey: SceneRecipeKey;
  conversationId: string;
  assistantMessageId: string;
};

const IDENTIFIER = /^[a-zA-Z0-9:_-]{1,160}$/;
const HINTS: Record<SceneRecipeKey, RegExp> = {
  forest: /\b(?:forest|woodland|woodlands)\b/i,
  village: /\b(?:village|hamlet|settlement|town square)\b/i,
  squad: /\b(?:party of heroes|hero squad|adventuring party)\b/i,
  armory: /\b(?:armou?ry|weapons room|weapon shop)\b/i,
  feast: /\b(?:tavern|feast|banquet)\b/i,
  lab: /\b(?:research lab|laboratory|robotic workshop|robotics lab)\b/i,
  garden: /\b(?:botanical garden|flower garden)\b/i,
  shrine: /\b(?:sacred shrine|temple shrine)\b/i,
  dungeon: /\b(?:dungeon|catacombs)\b/i,
  treasury: /\b(?:royal treasury|treasure vault)\b/i,
};

function id(value: unknown): value is string {
  return typeof value === 'string' && IDENTIFIER.test(value);
}

export function suggestedSceneRecipe(text: string): SceneRecipeKey | null {
  if (typeof text !== 'string' || text.length > 16000) return null;
  const matching = SCENE_RECIPES.filter(recipe => HINTS[recipe.key].test(text));
  // Do not silently choose between two or more equally plausible scenes.
  return matching.length === 1 ? matching[0].key : null;
}

export function prepareSceneChatHandoff(values: {
  id: string;
  createdAt: number;
  buildId: string;
  era: SceneEra;
  recipeKey: SceneRecipeKey;
  conversationId: string;
  assistantMessageId: string;
}): SceneChatHandoff {
  if (!id(values.id) || !id(values.conversationId) || !id(values.assistantMessageId)) {
    throw new Error('Invalid scene handoff identity.');
  }
  if (!validProjectId(values.buildId)) {
    throw new Error('Select a valid existing game build ID.');
  }
  if (!SCENE_ERAS.includes(values.era) ||
      !SCENE_RECIPES.some(recipe => recipe.key === values.recipeKey)) {
    throw new Error('Unsupported scene era or recipe.');
  }
  if (!Number.isSafeInteger(values.createdAt) || values.createdAt <= 0) {
    throw new Error('Invalid scene handoff timestamp.');
  }
  return {
    version: 1,
    id: values.id,
    createdAt: values.createdAt,
    buildId: values.buildId,
    era: values.era,
    recipeKey: values.recipeKey,
    conversationId: values.conversationId,
    assistantMessageId: values.assistantMessageId,
  };
}

export function readSceneChatHandoff(
  raw: string | null,
  expectedId: string,
  expectedBuildId: string,
  now = Date.now(),
): SceneChatHandoff | null {
  if (!raw || raw.length > 2048 || !id(expectedId) || !validProjectId(expectedBuildId) ||
      !Number.isSafeInteger(now)) return null;
  try {
    const value = JSON.parse(raw);
    if (!value || typeof value !== 'object' || Array.isArray(value) || value.version !== 1 ||
        value.id !== expectedId || value.buildId !== expectedBuildId ||
        !Number.isSafeInteger(value.createdAt) ||
        value.createdAt > now + 60_000 ||
        now - value.createdAt > SCENE_CHAT_MAX_AGE_MS) return null;
    return prepareSceneChatHandoff(value);
  } catch {
    return null;
  }
}

export function sceneHandoffItems(value: SceneChatHandoff): {
  category: string;
  count: number;
}[] {
  const recipe = SCENE_RECIPES.find(item => item.key === value.recipeKey);
  if (!recipe) return [];
  return recipe.items.map(item => ({ category: item.category, count: item.count }));
}
