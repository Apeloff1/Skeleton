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
  campaign_recipe_count: number;
  chronicle_recipe_count: number;
  epoch_recipe_count: number;
  saga_recipe_count: number;
  epic_recipe_count: number;
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
      || doc.recipe_catalog_count !== 49999999999500 || doc.catalog_total !== 50000000000000
      || doc.classic_recipe_count !== 4500 || doc.expanded_recipe_count !== 45000
      || doc.directed_recipe_count !== 450000 || doc.final_recipe_count !== 4500000 || doc.worldline_recipe_count !== 45000000 || doc.phase_recipe_count !== 450000000 || doc.campaign_recipe_count !== 4500000000 || doc.chronicle_recipe_count !== 45000000000 || doc.epoch_recipe_count !== 450000000000 || doc.saga_recipe_count !== 4500000000000 || doc.epic_recipe_count !== 45000000000000
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
  if (!Array.isArray(result.actions) || result.actions.length !== 500 || result.action_count !== 50000000000000)
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
  campaign?: string; campaign_index?: number; campaign_objective?: string;
  chronicle?: string; chronicle_index?: number; chronicle_objective?: string;
  epoch?: string; epoch_index?: number; epoch_objective?: string;
  saga?: string; saga_index?: number; saga_objective?: string;
  epic?: string; epic_index?: number; epic_objective?: string;
  treatment: string; recipe_steps: string[]; source_index: number;
  style_index: number; actual_project_mutation: boolean;
};
export type ForgeRecipeResults = {
  schema: 'skeleton.forge.production_recipe_search.v1';
  total_catalog: number; matched: number; offset: number; limit: number;
  next_offset: number | null; domains: string[]; styles: string[];
  system_layers?: string[]; directors?: string[]; finishes?: string[];
  worldlines?: string[]; campaigns?: string[]; chronicles?: string[]; epochs?: string[]; sagas?: string[]; epics?: string[];
  items: ForgeRecipe[];
};
export async function searchForgeRecipes(query = '', domain = '', offset = 0,
                                         limit = 32, generation: 'classic' | 'expanded' | 'directed' | 'final' | 'worldline' | 'phase' | 'campaign' | 'chronicle' | 'epoch' | 'saga' | 'epic' = 'classic',
                                         systemLayer = '', director = '', finish = '', worldline = '', phase = '', campaign = '', chronicle = '', epoch = '', saga = '', epic = ''): Promise<ForgeRecipeResults> {
  const params = [
    'query=' + encodeURIComponent(query),
    'generation=' + encodeURIComponent(generation),
    'system_layer=' + encodeURIComponent(systemLayer),
    'director=' + encodeURIComponent(director),
    'finish=' + encodeURIComponent(finish),
    'worldline=' + encodeURIComponent(worldline),
    'phase=' + encodeURIComponent(phase),
    'campaign=' + encodeURIComponent(campaign),
    'chronicle=' + encodeURIComponent(chronicle),
    'epoch=' + encodeURIComponent(epoch),
    'saga=' + encodeURIComponent(saga),
    'epic=' + encodeURIComponent(epic),
    'domain=' + encodeURIComponent(domain),
    'offset=' + encodeURIComponent(String(offset)),
    'limit=' + encodeURIComponent(String(limit)),
  ].join('&');
  const results = await data(api.get<ForgeRecipeResults>(
    ROOT + '/recipes?' + params, options()), 'Could not search original-game production recipes.');
  if (!results || results.schema !== 'skeleton.forge.production_recipe_search.v1'
      || results.total_catalog !== (generation === 'epic' ? 45000000000000 : generation === 'saga' ? 4500000000000 : generation === 'epoch' ? 450000000000 : generation === 'chronicle' ? 45000000000 : generation === 'campaign' ? 4500000000 : generation === 'phase' ? 450000000 : generation === 'worldline' ? 45000000 : generation === 'final' ? 4500000 : generation === 'directed' ? 450000 : generation === 'expanded' ? 45000 : 4500)
      || !Array.isArray(results.items)
      || results.items.length > 64
      || results.items.some(recipe => !(generation === 'classic' ? /^produce_[a-z_]+__[a-z_]+$/.test(recipe.operation)
          : generation === 'expanded' ? /^expand_[a-z_]+__[a-z_]+___[a-z_]+$/.test(recipe.operation)
          : generation === 'directed' ? /^direct_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+$/.test(recipe.operation)
          : generation === 'final' ? /^complete_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+$/.test(recipe.operation)
          : generation === 'worldline' ? /^worldline_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+$/.test(recipe.operation)
          : generation === 'phase' ? /^phase_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+$/.test(recipe.operation)
          : generation === 'epic' ? /^epic_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+___________[a-z_]+____________[a-z_]+$/.test(recipe.operation)
          : generation === 'saga' ? /^saga_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+___________[a-z_]+$/.test(recipe.operation)
          : generation === 'epoch' ? /^epoch_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+$/.test(recipe.operation)
          : generation === 'chronicle' ? /^chronicle_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+$/.test(recipe.operation)
          : /^campaign_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+$/.test(recipe.operation))
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

export type ForgeCampaignRank = {
  rank: number; campaign: string; path: string; quality_score: number;
  quality_max: number; quality_kind: string; words: number; characters: number;
  bytes: number; content_sha256: string; criteria: Record<string, boolean>;
};
export type ForgeCampaignRanking = {
  schema: 'skeleton.forge.campaign_handbook_ranking.v1';
  sort: 'quality' | 'length';
  scope: 'ten_campaign_variants_for_one_exact_production_context';
  compared: 10; items: ForgeCampaignRank[];
};
export async function rankForgeCampaignHandbooks(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, sort: 'quality' | 'length' = 'quality',
): Promise<ForgeCampaignRanking> {
  const parts = [domain,treatment,director,worldline,phase];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid Forge game handbook comparison scope.');
  const route = ROOT + '/campaign-handbooks/rank/' +
    parts.map(encodeURIComponent).join('/')+'?sort='+sort;
  const ranked = await data(api.get<ForgeCampaignRanking>(route,options()),
    'Could not rank source-backed game production manuscripts.');
  if (!ranked || ranked.schema !== 'skeleton.forge.campaign_handbook_ranking.v1'
      || ranked.scope !== 'ten_campaign_variants_for_one_exact_production_context'
      || ranked.sort !== sort || ranked.compared !== 10
      || !Array.isArray(ranked.items) || ranked.items.length !== 10
      || ranked.items.some(item => !SHA.test(item.content_sha256)
        || !Number.isFinite(item.quality_score)
        || item.quality_score < 0 || item.quality_score > 100
        || !Number.isSafeInteger(item.words) || item.words < 1))
    throw new Error('Forge manuscript comparison contract invalid.');
  return ranked;
}
export async function readForgeCampaignHandbook(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string,
): Promise<{ markdown: string; score: number; words: number }> {
  const parts = [domain,treatment,director,worldline,phase,campaign];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid Forge campaign manuscript identity.');
  const book = await data(api.get<{schema: string; markdown: string;
    quality_score: number; content_sha256: string; words: number;
    covered_commands: number}>(
    ROOT+'/campaign-handbooks/'+parts.map(encodeURIComponent).join('/'),
    options()), 'Unable to read the original game-production campaign manual.');
  if (book.schema !== 'skeleton.forge.campaign_handbook.v1'
      || !SHA.test(book.content_sha256)
      || book.covered_commands !== 5000
      || typeof book.markdown !== 'string' || book.markdown.length > 128000
      || !Number.isSafeInteger(book.words) || book.words < 1
      || !Number.isFinite(book.quality_score))
    throw new Error('Invalid source-derived Forge campaign manual.');
  return { markdown: book.markdown, score: book.quality_score, words: book.words };
}


export type ForgeChronicleRank = {
  rank: number; chronicle: string; path: string; quality_score: number;
  quality_max: number; quality_kind: string; words: number; characters: number;
  bytes: number; content_sha256: string; criteria: Record<string, boolean>;
};
export type ForgeChronicleRanking = {
  schema: 'skeleton.forge.chronicle_handbook_ranking.v1';
  sort: 'quality' | 'length';
  scope: 'ten_chronicle_variants_for_one_exact_campaign_context';
  compared: 10; items: ForgeChronicleRank[];
};
export async function readForgeChronicleHandbook(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string,
): Promise<{ markdown: string; score: number; words: number }> {
  const parts = [domain,treatment,director,worldline,phase,campaign,chronicle];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid exact chronicle manuscript identity.');
  const book = await data(api.get<{schema: string; markdown: string;
    quality_score: number; content_sha256: string; words: number;
    covered_commands: number}>(
    ROOT+'/chronicle-handbooks/'+parts.map(encodeURIComponent).join('/'),
    options()), 'Unable to render exact original-game chronicle manual.');
  if (book.schema !== 'skeleton.forge.chronicle_handbook.v1'
      || !SHA.test(book.content_sha256) || book.covered_commands !== 5000
      || typeof book.markdown !== 'string' || book.markdown.length > 192000
      || !Number.isSafeInteger(book.words) || book.words < 1
      || !Number.isFinite(book.quality_score) || book.quality_score < 0
      || book.quality_score > 100)
    throw new Error('Chronicle manuscript failed source integrity validation.');
  return {markdown: book.markdown, score: book.quality_score, words: book.words};
}
export async function rankForgeChronicleHandbooks(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, sort: 'quality' | 'length' = 'quality',
): Promise<ForgeChronicleRanking> {
  const parts = [domain,treatment,director,worldline,phase,campaign];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid comparable chronicle source context.');
  const ranked = await data(api.get<ForgeChronicleRanking>(
    ROOT+'/chronicle-handbooks/rank/'+parts.map(encodeURIComponent).join('/')
      +'?sort='+sort, options()), 'Unable to rank chronicle source manuscripts.');
  if (!ranked || ranked.schema !== 'skeleton.forge.chronicle_handbook_ranking.v1'
      || ranked.scope !== 'ten_chronicle_variants_for_one_exact_campaign_context'
      || ranked.sort !== sort || ranked.compared !== 10
      || !Array.isArray(ranked.items) || ranked.items.length !== 10
      || ranked.items.some(item => !SHA.test(item.content_sha256)
        || !Number.isFinite(item.quality_score) || item.quality_score < 0
        || item.quality_score > 100 || !Number.isSafeInteger(item.words)
        || item.words < 1))
    throw new Error('Chronicle manuscript comparison contract invalid.');
  return ranked;
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
      steps.some(step => typeof step.action !== 'string' || step.action.length > 512 || !doc.action_catalog.includes(step.action)
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
          && /^phase_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+$/.test(step.action))
        && !(doc.campaign_recipe_count === 4500000000
          && /^campaign_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+$/.test(step.action))
        && !(doc.chronicle_recipe_count === 45000000000
          && /^chronicle_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+$/.test(step.action))
        && !(doc.epoch_recipe_count === 450000000000
          && /^epoch_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+$/.test(step.action))
        && !(doc.saga_recipe_count === 4500000000000
          && /^saga_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+___________[a-z_]+$/.test(step.action))
        && !(doc.epic_recipe_count === 45000000000000
          && /^epic_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+___________[a-z_]+____________[a-z_]+$/.test(step.action)))) throw new Error(
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

export type ForgeEpochRank = {
  rank: number; epoch: string; path: string; quality_score: number;
  quality_max: number; quality_kind: string; words: number; characters: number;
  bytes: number; content_sha256: string; criteria: Record<string, boolean>;
};
export type ForgeEpochRanking = {
  schema: 'skeleton.forge.epoch_handbook_ranking.v1';
  sort: 'quality' | 'length';
  scope: 'ten_rendered_epoch_variants_for_one_exact_chronicle';
  compared: 10; items: ForgeEpochRank[];
};

/** Exact server-rendered, SHA-addressed source handbook, not creative merit. */
export async function readForgeEpochHandbook(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string, epoch: string,
): Promise<{ markdown: string; score: number; words: number }> {
  const parts = [domain,treatment,director,worldline,phase,campaign,chronicle,epoch];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid original-game temporal manual identity.');
  const book = await data(api.get<{schema: string; markdown: string; content_sha256: string;
    quality_score: number; words: number; covered_commands: number}>(
    ROOT + '/epoch-handbooks/' + parts.map(encodeURIComponent).join('/'), options()),
    'Unable to render exact temporal source manual.');
  if (!book || book.schema !== 'skeleton.forge.epoch_handbook.v1'
      || !SHA.test(book.content_sha256) || book.covered_commands !== 5000
      || typeof book.markdown !== 'string' || book.markdown.length > 256000
      || !Number.isSafeInteger(book.words) || book.words < 1
      || !Number.isFinite(book.quality_score) || book.quality_score < 0
      || book.quality_score > 100)
    throw new Error('Temporal source manuscript failed protocol validation.');
  return {markdown: book.markdown, score: book.quality_score, words: book.words};
}

export async function rankForgeEpochHandbooks(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string,
  sort: 'quality' | 'length' = 'quality',
): Promise<ForgeEpochRanking> {
  const parts = [domain,treatment,director,worldline,phase,campaign,chronicle];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid shared temporal handbook comparison scope.');
  const ranking = await data(api.get<ForgeEpochRanking>(
    ROOT + '/epoch-handbooks/rank/' + parts.map(encodeURIComponent).join('/')
      + '?sort=' + sort, options()), 'Unable to compare rendered epoch manuals.');
  if (!ranking || ranking.schema !== 'skeleton.forge.epoch_handbook_ranking.v1'
      || ranking.scope !== 'ten_rendered_epoch_variants_for_one_exact_chronicle'
      || ranking.sort !== sort || ranking.compared !== 10
      || !Array.isArray(ranking.items) || ranking.items.length !== 10
      || ranking.items.some(item => !SHA.test(item.content_sha256)
        || !Number.isFinite(item.quality_score) || item.quality_score < 0
        || item.quality_score > 100 || !Number.isSafeInteger(item.words)
        || item.words < 1))
    throw new Error('Temporal handbook comparison protocol invalid.');
  return ranking;
}


/** Source-tile route replay. This checks deterministic reference movement,
 * not native engine execution or shipping-grade playthrough certification. */
export type ForgeRouteScenario = {
  scenario_id: string; layer: string; start: [number, number];
  goal: [number, number]; require_alternate: boolean;
};
export type ForgeRouteWitness = {
  reachable: boolean; steps: number | null; path_sha256: string | null;
  path_sample: [number, number][]; sample_truncated: boolean;
};
export type ForgeRouteAudit = {
  schema: 'skeleton.forge.route_playthrough_assurance.v1';
  project_id: string; project_sha256: string; source_version: number;
  scenario_count: number; passed_count: number; failed_count: number;
  scenarios: Array<ForgeRouteScenario & {
    source_layer_sha256: string; primary: ForgeRouteWitness;
    alternate: ForgeRouteWitness | null; passed: boolean; failure: string | null;
  }>;
  receipt_sha256: string;
  verified_against_authoritative_source: true;
  reference_source_replay: true;
  native_engine_executed: false; release_certified: false;
};
function boundedTilePoint(point: readonly number[]): boolean {
  return Array.isArray(point) && point.length === 2 &&
    point.every(value => Number.isInteger(value) && value >= 0 && value <= 255);
}
function checkRouteWitness(witness: ForgeRouteWitness | null): boolean {
  return !!witness && typeof witness.reachable === 'boolean' &&
    (witness.steps === null || (Number.isSafeInteger(witness.steps) && witness.steps >= 0)) &&
    (witness.path_sha256 === null || SHA.test(witness.path_sha256)) &&
    Array.isArray(witness.path_sample) && witness.path_sample.length <= 256 &&
    witness.path_sample.every(boundedTilePoint) &&
    typeof witness.sample_truncated === 'boolean' &&
    (!witness.reachable || (witness.steps !== null && SHA.test(witness.path_sha256 || '')));
}
export async function auditForgeRoutes(
  projectId: string, scenarios: ForgeRouteScenario[], signal?: AbortSignal,
): Promise<ForgeRouteAudit> {
  if (!Array.isArray(scenarios) || scenarios.length < 1 || scenarios.length > 100 ||
      new Set(scenarios.map(row => row.scenario_id)).size !== scenarios.length ||
      scenarios.some(row => !row || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(row.scenario_id) ||
        typeof row.layer !== 'string' || row.layer.length < 1 || row.layer.length > 128 ||
        !boundedTilePoint(row.start) || !boundedTilePoint(row.goal) ||
        (row.start[0] === row.goal[0] && row.start[1] === row.goal[1]) ||
        typeof row.require_alternate !== 'boolean')) {
    throw new ChatClientError('Invalid bounded source-route inspection request.',
      { kind: 'protocol', retryable: false });
  }
  const report = await data(api.post<ForgeRouteAudit>(
    route(projectId) + '/routes/audit', {scenarios}, options(undefined, signal)),
    'Could not verify authored routes.');
  if (!report || report.schema !== 'skeleton.forge.route_playthrough_assurance.v1' ||
      report.project_id !== projectId || !SHA.test(report.project_sha256) ||
      !SHA.test(report.receipt_sha256) || !Number.isSafeInteger(report.source_version) ||
      !Number.isSafeInteger(report.passed_count) || !Number.isSafeInteger(report.failed_count) ||
      report.scenario_count !== scenarios.length ||
      report.passed_count + report.failed_count !== report.scenario_count ||
      report.verified_against_authoritative_source !== true ||
      report.reference_source_replay !== true ||
      report.native_engine_executed !== false || report.release_certified !== false ||
      !Array.isArray(report.scenarios) || report.scenarios.length !== scenarios.length ||
      report.scenarios.some((entry, index) => entry.scenario_id !== scenarios[index].scenario_id ||
        entry.layer !== scenarios[index].layer ||
        entry.require_alternate !== scenarios[index].require_alternate ||
        entry.start.join(',') !== scenarios[index].start.join(',') ||
        entry.goal.join(',') !== scenarios[index].goal.join(',') ||
        !SHA.test(entry.source_layer_sha256) ||
        !checkRouteWitness(entry.primary) ||
        (entry.require_alternate
          ? !checkRouteWitness(entry.alternate)
          : entry.alternate !== null) ||
        typeof entry.passed !== 'boolean')) {
    throw new ChatClientError('Forge route replay returned inconsistent or unverified evidence.',
      { kind: 'protocol', retryable: false });
  }
  return report;
}

export type ForgeSagaRank = {
  rank: number; saga: string; path: string; quality_score: number;
  quality_max: number; quality_kind: string; words: number; characters: number;
  bytes: number; content_sha256: string; criteria: Record<string, boolean>;
};
export type ForgeSagaRanking = {
  schema: 'skeleton.forge.saga_handbook_ranking.v1';
  sort: 'quality' | 'length';
  scope: 'ten_rendered_saga_variants_for_one_exact_epoch_context';
  compared: 10; items: ForgeSagaRank[];
};

/** Strict client contract for an actually rendered source-grounded Saga manual. */
export async function readForgeSagaHandbook(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string, epoch: string, saga: string,
): Promise<{ markdown: string; score: number; words: number }> {
  const parts = [domain, treatment, director, worldline, phase, campaign, chronicle, epoch, saga];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid exact source-backed saga identity.');
  const book = await data(api.get<{schema: string; markdown: string; content_sha256: string;
    quality_score: number; words: number; covered_commands: number}>(
    ROOT + '/saga-handbooks/' + parts.map(encodeURIComponent).join('/'), options()),
    'Unable to read original-game saga documentation.');
  if (!book || book.schema !== 'skeleton.forge.saga_handbook.v1'
      || !SHA.test(book.content_sha256) || book.covered_commands !== 5000
      || typeof book.markdown !== 'string' || book.markdown.length > 384000
      || !Number.isSafeInteger(book.words) || book.words < 1
      || !Number.isFinite(book.quality_score) || book.quality_score < 0
      || book.quality_score > 100)
    throw new Error('Saga handbook failed source protocol checks.');
  return {markdown: book.markdown, score: book.quality_score, words: book.words};
}

export async function rankForgeSagaHandbooks(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string, epoch: string,
  sort: 'quality' | 'length' = 'quality',
): Promise<ForgeSagaRanking> {
  const parts = [domain, treatment, director, worldline, phase, campaign, chronicle, epoch];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid exact comparison context for Saga manuals.');
  const ranking = await data(api.get<ForgeSagaRanking>(
    ROOT + '/saga-handbooks/rank/' + parts.map(encodeURIComponent).join('/')
      + '?sort=' + sort, options()), 'Unable to rank real saga manuscripts.');
  if (!ranking || ranking.schema !== 'skeleton.forge.saga_handbook_ranking.v1'
      || ranking.scope !== 'ten_rendered_saga_variants_for_one_exact_epoch_context'
      || ranking.sort !== sort || ranking.compared !== 10
      || !Array.isArray(ranking.items) || ranking.items.length !== 10
      || ranking.items.some(item => !SHA.test(item.content_sha256)
        || !Number.isFinite(item.quality_score) || item.quality_score < 0
        || item.quality_score > 100 || !Number.isSafeInteger(item.words)
        || item.words < 1))
    throw new Error('Saga manuscript ranking failed protocol validation.');
  return ranking;
}

export type ForgeEpicRank = {
  rank: number; epic: string; path: string;
  quality_score: number; quality_max: number; quality_kind: string;
  words: number; characters: number; bytes: number; content_sha256: string;
  criteria: Record<string, boolean>;
};
export type ForgeEpicRanking = {
  schema: 'skeleton.forge.epic_handbook_ranking.v1';
  sort: 'quality' | 'length';
  scope: 'ten_actually_rendered_epic_variants_with_exact_saga_context';
  compared: 10; items: ForgeEpicRank[];
};

export async function readForgeEpicHandbook(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string, epoch: string,
  saga: string, epic: string,
): Promise<{ markdown: string; score: number; words: number }> {
  const parts = [domain, treatment, director, worldline, phase,
    campaign, chronicle, epoch, saga, epic];
  if (parts.some(p => !/^[a-z][a-z_]{0,40}$/.test(p)))
    throw new Error('Exact registered Epic manual identity required.');
  const doc = await data(api.get<{
    schema: string; markdown: string; content_sha256: string;
    quality_score: number; words: number; covered_commands: number;
  }>(ROOT + '/epic-handbooks/' + parts.map(encodeURIComponent).join('/'),
     options()), 'Unable to read Epic world-production handbook.');
  if (!doc || doc.schema !== 'skeleton.forge.epic_handbook.v1'
      || !SHA.test(doc.content_sha256) || doc.covered_commands !== 5000
      || typeof doc.markdown !== 'string' || doc.markdown.length > 512000
      || !Number.isFinite(doc.quality_score) || doc.quality_score < 0
      || doc.quality_score > 100 || !Number.isSafeInteger(doc.words) || doc.words < 1)
    throw new Error('Epic handbook failed typed integrity checks.');
  return {markdown: doc.markdown, score: doc.quality_score, words: doc.words};
}

export async function rankForgeEpicHandbooks(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string, epoch: string,
  saga: string, sort: 'quality' | 'length' = 'quality',
): Promise<ForgeEpicRanking> {
  const parts = [domain, treatment, director, worldline, phase,
    campaign, chronicle, epoch, saga];
  if (parts.some(p => !/^[a-z][a-z_]{0,40}$/.test(p)))
    throw new Error('Exact context needed for Epic manual comparison.');
  const response = await data(api.get<ForgeEpicRanking>(
    ROOT + '/epic-handbooks/rank/' + parts.map(encodeURIComponent).join('/')
      + '?sort=' + sort, options()), 'Unable to compare Epic manuals.');
  if (!response || response.schema !== 'skeleton.forge.epic_handbook_ranking.v1'
      || response.scope !== 'ten_actually_rendered_epic_variants_with_exact_saga_context'
      || response.compared !== 10 || response.sort !== sort
      || !Array.isArray(response.items) || response.items.length !== 10
      || response.items.some(item => !SHA.test(item.content_sha256)
        || !Number.isFinite(item.quality_score) || item.quality_score < 0
        || item.quality_score > 100 || !Number.isSafeInteger(item.words)
        || item.words < 1))
    throw new Error('Epic handbook ranking violates strict source contract.');
  return response;
}

/** Source-only cross-layer route audit; transport proposals are NOT native moves. */
export type ForgeEpicWaypoint = { layer: string; x: number; y: number };
export type ForgeEpicTransfer = {
  connector_id: string; from: ForgeEpicWaypoint; to: ForgeEpicWaypoint;
  mode: 'walk' | 'stairs' | 'elevator' | 'bridge' | 'ferry' | 'shuttle' | 'portal';
  bidirectional: boolean;
};
export type ForgeEpicJourney = {
  journey_id: string; start: ForgeEpicWaypoint; goal: ForgeEpicWaypoint;
  require_alternate: boolean;
};
export type ForgeEpicRouteRequest = {
  layer_ids: string[]; connectors: ForgeEpicTransfer[];
  itineraries: ForgeEpicJourney[];
};
export type ForgeEpicRouteWitness = {
  reachable: boolean; steps: number | null; transfers: number;
  connector_ids: string[]; path_sha256: string | null;
  sample: [string, number, number][];
  sample_truncated: boolean;
};
export type ForgeEpicRouteAudit = {
  schema: 'skeleton.forge.epic_interlayer_reference.v1';
  project_id: string; project_sha256: string; source_version: number;
  layer_ids: string[]; layer_source_sha256: Record<string, string>;
  connectors: { connector_id: string; mode: string; distance_m: number }[];
  journey_count: number; passed_count: number; failed_count: number;
  journeys: {
    journey_id: string; start: [string, number, number];
    goal: [string, number, number]; require_alternate: boolean;
    primary: ForgeEpicRouteWitness; alternate: ForgeEpicRouteWitness | null;
    passed: boolean; failure: string | null;
  }[];
  receipt_sha256: string; verified_against_authoritative_source: true;
  native_engine_executed: false; transport_actions_applied: false;
  release_certified: false; source_reference_only: true;
};
export async function auditForgeEpicRoutes(
  projectId: string, body: ForgeEpicRouteRequest,
): Promise<ForgeEpicRouteAudit> {
  if (!Array.isArray(body.layer_ids) || body.layer_ids.length < 1 ||
      body.layer_ids.length > 8 || new Set(body.layer_ids).size !== body.layer_ids.length ||
      !Array.isArray(body.connectors) || body.connectors.length > 64 ||
      !Array.isArray(body.itineraries) || body.itineraries.length < 1 ||
      body.itineraries.length > 32)
    throw new Error('Epic route audit requires 1..8 unique layers, <=64 transfers, and 1..32 journeys.');
  const result = await data(api.post<ForgeEpicRouteAudit>(
    route(projectId) + '/epic-routes/audit', body, options()
  ), 'Could not replay Epic multi-layer itineraries from the saved project.');
  const witness = (value: ForgeEpicRouteWitness | null): value is ForgeEpicRouteWitness =>
    !!value && typeof value.reachable === 'boolean'
      && (value.path_sha256 === null || SHA.test(value.path_sha256))
      && Array.isArray(value.sample) && value.sample.length <= 128
      && value.sample.every(node =>
        Array.isArray(node) && node.length === 3 && typeof node[0] === 'string'
        && Number.isSafeInteger(node[1]) && Number.isSafeInteger(node[2]))
      && Number.isSafeInteger(value.transfers) && value.transfers >= 0
      && Array.isArray(value.connector_ids);
  if (!result || result.schema !== 'skeleton.forge.epic_interlayer_reference.v1'
      || result.project_id !== projectId || !SHA.test(result.project_sha256)
      || !SHA.test(result.receipt_sha256) || !Number.isSafeInteger(result.source_version)
      || result.source_reference_only !== true
      || result.native_engine_executed !== false
      || result.transport_actions_applied !== false
      || result.release_certified !== false
      || result.verified_against_authoritative_source !== true
      || !Array.isArray(result.layer_ids) || !Array.isArray(result.connectors)
      || !Array.isArray(result.journeys)
      || result.journey_count !== body.itineraries.length
      || result.passed_count + result.failed_count !== result.journey_count
      || result.journeys.some(j => typeof j.passed !== 'boolean'
          || !witness(j.primary)
          || (j.require_alternate ? !witness(j.alternate) : j.alternate !== null))) {
    throw new ChatClientError('Epic multi-layer route report failed replay contract checks.',
      {kind: 'protocol', retryable: false});
  }
  return result;
}
