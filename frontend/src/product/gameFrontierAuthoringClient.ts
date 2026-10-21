/** Authenticated client for real Forge Studio tile, actor, quest and game creation. */
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders } from '../auth/gameforgeAuth';
import { chatApiError, ChatClientError } from './chatErrors';
import { learningRequestKey } from './gameLearningClient';

const ROOT = '/api/game-frontier-authoring';
const SHA = /^[a-f0-9]{64}$/;

export type ForgeLayer = {
  id: string; size: [number, number]; tile_count: number; palette_size: number; elevation_m: number;
};
export type ForgeDocument = {
  schema: 'skeleton.game.frontier_studio_document.v1';
  project_id: string; expected_version: number; source_sha256: string;
  layers: ForgeLayer[]; prefab_count: number; placed_actor_count: number;
  authored_event_count: number; quest_count: number; music_cue_count: number;
  prefab_catalog?: { id: string; kind: string; era: string; interaction: string }[];
  actor_catalog?: { index: number; prefab_id: string; position: [number,number,number]; facing_deg: number }[];
  quest_catalog?: { id: string; title: string; stage_count: number }[];
  action_catalog: string[]; already_saved: boolean;
  recipe_catalog_count: number; catalog_total: number; recipe_search_required: boolean;
  classic_recipe_count: number; expanded_recipe_count: number;
  directed_recipe_count: number;
  final_recipe_count: number;
  worldline_recipe_count: number;
  phase_recipe_count: number;
};
export type ForgeStep = { action: string; parameters: Record<string, unknown> };
export type ForgePreview = {
  candidate_sha256: string; source_sha256: string; persisted: false;
  batch_receipt: { action_count: number; actually_changed: boolean; receipt_sha256: string };
  summary: ForgeDocument;
};
export type ForgeCommit = {
  project_id: string; expected_version: number; source_sha256: string; persisted: true;
  summary: ForgeDocument;
};
export type ForgeBuild = {
  project_id: string; source_sha256: string; game_world_sha256?: string;
  world_sha256?: string; travel_edges?: number; world_nodes?: number; file_count?: number;
  file_paths?: string[]; saved?: boolean; receipt_sha256?: string;
  native_engine_executed: false; release_certified: false;
};

function options(key?: string, signal?: AbortSignal) {
  return { headers: authHeaders(), idempotencyKey: key, signal, retries: 0, timeoutMs: 40000 };
}
async function data<T>(response: Promise<ApiResult<T>>, message: string): Promise<T> {
  const result = await response;
  if (!result.ok || result.data === null) throw chatApiError(result, message);
  return result.data;
}
function route(projectId: string) {
  if (!projectId || projectId.length > 128) throw new ChatClientError(
    'Invalid Forge Studio project identity.', { kind: 'protocol', retryable: false });
  return ROOT + '/projects/' + encodeURIComponent(projectId);
}
function verifyDoc(doc: ForgeDocument): ForgeDocument {
  if (!doc || doc.schema !== 'skeleton.game.frontier_studio_document.v1'
      || !SHA.test(doc.source_sha256) || !Number.isSafeInteger(doc.expected_version)
      || !Array.isArray(doc.action_catalog) || doc.action_catalog.length !== 500
      || doc.recipe_catalog_count !== 499999500 || doc.catalog_total !== 500000000
      || doc.classic_recipe_count !== 4500 || doc.expanded_recipe_count !== 45000
      || doc.directed_recipe_count !== 450000 || doc.final_recipe_count !== 4500000 || doc.worldline_recipe_count !== 45000000 || doc.phase_recipe_count !== 450000000
      || !Array.isArray(doc.layers) || doc.layers.length > 128
      || (doc.prefab_catalog !== undefined && !Array.isArray(doc.prefab_catalog))
      || (doc.actor_catalog !== undefined && !Array.isArray(doc.actor_catalog))
      || (doc.quest_catalog !== undefined && !Array.isArray(doc.quest_catalog))) {
    throw new ChatClientError('Forge Studio returned invalid original game authoring source.',
      { kind: 'protocol', retryable: false });
  }
  return doc;
}

export async function inspectForge(projectId: string, signal?: AbortSignal): Promise<ForgeDocument> {
  return verifyDoc(await data(api.get<ForgeDocument>(route(projectId), options(undefined, signal)),
    'Failed to load the authored game.'));
}
export async function getForgeActions(signal?: AbortSignal): Promise<string[]> {
  const result = await data(api.get<{ actions: string[]; action_count: number }>(
    ROOT + '/actions', options(undefined, signal)), 'Forge tool catalogue unavailable.');
  if (!Array.isArray(result.actions) || result.actions.length !== 500 || result.action_count !== 500000000)
    throw new Error('Forge Studio action catalogue is incomplete.');
  return result.actions;
}
export type ForgeRecipe = {
  operation: string; domain: string; source_blueprint: string;
  base_operation?: string; system_layer?: string; system_layer_index?: number;
  direction?: string; director_index?: number; director_purpose?: string;
  finish?: string; finish_index?: number; finish_objective?: string;
  worldline?: string; worldline_index?: number; worldline_objective?: string;
  phase?: string; phase_index?: number; phase_objective?: string;
  treatment: string; recipe_steps: string[]; source_index: number;
  style_index: number; actual_project_mutation: boolean;
};
export type ForgeRecipeResults = {
  schema: 'skeleton.forge.production_recipe_search.v1';
  total_catalog: number; matched: number; offset: number; limit: number;
  next_offset: number | null; domains: string[]; styles: string[];
  system_layers?: string[]; directors?: string[]; finishes?: string[];
  worldlines?: string[];
  items: ForgeRecipe[];
};
export async function searchForgeRecipes(query = '', domain = '', offset = 0,
                                         limit = 32, generation: 'classic' | 'expanded' | 'directed' | 'final' | 'worldline' | 'phase' = 'classic',
                                         systemLayer = '', director = '', finish = '', worldline = '', phase = ''): Promise<ForgeRecipeResults> {
  const params = [
    'query=' + encodeURIComponent(query),
    'generation=' + encodeURIComponent(generation),
    'system_layer=' + encodeURIComponent(systemLayer),
    'director=' + encodeURIComponent(director),
    'finish=' + encodeURIComponent(finish),
    'worldline=' + encodeURIComponent(worldline),
    'phase=' + encodeURIComponent(phase),
    'domain=' + encodeURIComponent(domain),
    'offset=' + encodeURIComponent(String(offset)),
    'limit=' + encodeURIComponent(String(limit)),
  ].join('&');
  const results = await data(api.get<ForgeRecipeResults>(
    ROOT + '/recipes?' + params, options()), 'Could not search original-game production recipes.');
  if (!results || results.schema !== 'skeleton.forge.production_recipe_search.v1'
      || results.total_catalog !== (generation === 'phase' ? 450000000 : generation === 'worldline' ? 45000000 : generation === 'final' ? 4500000 : generation === 'directed' ? 450000 : generation === 'expanded' ? 45000 : 4500)
      || !Array.isArray(results.items)
      || results.items.length > 64
      || results.items.some(recipe => !(generation === 'classic' ? /^produce_[a-z_]+__[a-z_]+$/.test(recipe.operation)
          : generation === 'expanded' ? /^expand_[a-z_]+__[a-z_]+___[a-z_]+$/.test(recipe.operation)
          : generation === 'directed' ? /^direct_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+$/.test(recipe.operation)
          : generation === 'final' ? /^complete_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+$/.test(recipe.operation)
          : generation === 'worldline' ? /^worldline_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+$/.test(recipe.operation)
          : /^phase_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+$/.test(recipe.operation))
        || recipe.actual_project_mutation !== true)) {
    throw new ChatClientError('Forge production recipe search returned invalid source.',
      {kind: 'protocol', retryable: false});
  }
  return results;
}

export async function readForgeHandbook(domain: string, treatment: string,
                                         director: string, worldline: string): Promise<string> {
  const parts = [domain, treatment, director, worldline];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Unknown Forge technical handbook identity.');
  const response = await data(api.get<{schema: string; markdown: string;
    content_sha256: string; covered_commands: number}>(
    ROOT + '/handbooks/' + parts.map(encodeURIComponent).join('/'), options()),
    'Could not load the source-backed game-production handbook.');
  if (response.schema !== 'skeleton.forge.worldline_handbook.v1'
      || !SHA.test(response.content_sha256) || response.covered_commands !== 5000
      || typeof response.markdown !== 'string' || response.markdown.length > 64000)
    throw new Error('Forge handbook integrity contract invalid.');
  return response.markdown;
}

export async function readForgePhaseHandbook(domain: string, treatment: string,
  director: string, worldline: string, phase: string): Promise<string> {
  const parts = [domain, treatment, director, worldline, phase];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Unknown Forge phase handbook identity.');
  const response = await data(api.get<{schema: string; markdown: string;
    content_sha256: string; covered_commands: number}>(
    ROOT + '/phase-handbooks/' + parts.map(encodeURIComponent).join('/'), options()),
    'Could not load the phase game-production handbook.');
  if (response.schema !== 'skeleton.forge.phase_game_handbook.v1'
      || !SHA.test(response.content_sha256) || response.covered_commands !== 5000
      || typeof response.markdown !== 'string' || response.markdown.length > 96000)
    throw new Error('Forge phase handbook integrity contract invalid.');
  return response.markdown;
}

export async function copyForgeTiles(projectId: string, layer: string, x: number, y: number,
                                     width: number, height: number) {
  return data(api.post<{ tiles: number[]; palette: string[]; receipt_sha256: string }>(
    route(projectId) + '/tiles/copy', { layer, x, y, width, height },
    options()), 'Could not copy authored map region.');
}
export async function editForge(projectId: string, doc: ForgeDocument, steps: ForgeStep[],
                                preview: boolean): Promise<ForgePreview | ForgeCommit> {
  if (!Array.isArray(steps) || steps.length < 1 || steps.length > 64 ||
      steps.some(step => !doc.action_catalog.includes(step.action)
        && !(doc.classic_recipe_count === 4500
          && /^produce_[a-z_]+__[a-z_]+$/.test(step.action))
        && !(doc.expanded_recipe_count === 45000
          && /^expand_[a-z_]+__[a-z_]+___[a-z_]+$/.test(step.action))
        && !(doc.directed_recipe_count === 450000
          && /^direct_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+$/.test(step.action))
        && !(doc.final_recipe_count === 4500000
          && /^complete_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+$/.test(step.action))
        && !(doc.worldline_recipe_count === 45000000
          && /^worldline_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+$/.test(step.action))
        && !(doc.phase_recipe_count === 450000000
          && /^phase_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+$/.test(step.action)))) throw new Error(
    'Select one or more supported editor operations.');
  const key = learningRequestKey('forge-author');
  const body = { expected_version: doc.expected_version,
    expected_sha256: doc.source_sha256, idempotency_key: key, steps };
  if (preview) return data(api.post<ForgePreview>(route(projectId) + '/edits/preview',
    body, options(key)), 'Could not preview source edits.');
  return data(api.patch<ForgeCommit>(route(projectId) + '/edits',
    body, options(key)), 'Could not save source edits.');
}
export async function buildForge(projectId: string, seed: number, islands: number): Promise<ForgeBuild> {
  return data(api.post<ForgeBuild>(route(projectId) + '/build', {
    seed, islands, include_godot: false,
  }, options()), 'Could not compile the original game.');
}
export async function exportForge(projectId: string, doc: ForgeDocument,
                                  seed: number, islands: number): Promise<ForgeBuild> {
  const key = learningRequestKey('forge-export');
  return data(api.post<ForgeBuild>(route(projectId) + '/build/export', {
    expected_version: doc.expected_version, expected_sha256: doc.source_sha256,
    seed, islands, idempotency_key: key,
  }, options(key)), 'Could not publish native Godot files to the project.');
}


export type ForgeGameplayProbe = {
  source_sha256: string; occupied_zones: { zone_id: string; action_kind: string }[];
  field_forces: { field_id: string; force_xyz_n: number[] }[];
  net_force_xyz_n: number[];
  environment_accepted: { page_id: string; actions: unknown[] }[];
  missing_sensor_signals: string[]; native_engine_executed: false;
  receipt_sha256: string;
};
export async function previewForgeGameplay(projectId: string, position_xyz_m: number[],
                                          current_signals: Record<string, number>,
                                          flags: Record<string, boolean> = {}): Promise<ForgeGameplayProbe> {
  return data(api.post<ForgeGameplayProbe>(route(projectId) + '/gameplay/simulate', {
    position_xyz_m, mass_kg: 75, now_ms: 50000, current_signals, flags,
  }, options()), 'Could not evaluate authored gameplay at this position.');
}
