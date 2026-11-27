/** Authenticated client for real Forge Studio tile, actor, quest and game creation. */
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthEpoch, getAuthToken, initializeStoredToken } from '../auth/gameforgeAuth';
import { chatApiError, ChatClientError } from './chatErrors';
import { learningRequestKey } from './gameLearningClient';
import { cloneForgeEditInput } from '../features/Jeeves/forgeParameters/forgeQueuedSave';

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
  continuity_recipe_count: number;
};
export type ForgeStep = { action: string; parameters: Record<string, unknown> };
export type ForgeAuthoringSummary = Omit<ForgeDocument, 'schema' | 'expected_version' | 'already_saved'> & {
  schema: 'skeleton.forge.frontier_authoring_summary.v1'; candidate_only: true;
};
export type ForgePreview = {
  schema: 'skeleton.game.frontier_studio_preview.v1';
  candidate_sha256: string; source_sha256: string; persisted: false;
  batch_receipt: { action_count: number; actually_changed: boolean; receipt_sha256: string };
  summary: ForgeAuthoringSummary;
};
export type ForgeCommit = {
  schema: 'skeleton.game.frontier_studio_committed.v1';
  project_id: string; expected_version: number; source_sha256: string; persisted: true;
  summary: ForgeAuthoringSummary;
  request_id: string; origin_request_digest: string; original_source_sha256: string;
  head_version: number; replayed: boolean;
};
export type ForgeBuild = {
  project_id: string; source_sha256: string; game_world_sha256?: string;
  world_sha256?: string; travel_edges?: number; world_nodes?: number; file_count?: number;
  file_paths?: string[]; saved?: boolean; receipt_sha256?: string;
  native_engine_executed: false; release_certified: false;
};

/** A failed save is uncertain unless this first attempt is proven not dispatched. */
export class ForgeEditError extends ChatClientError {
  readonly preDispatch: boolean;
  constructor(error: unknown, preDispatch: boolean) {
    const known = error instanceof ChatClientError ? error : null;
    super(error instanceof Error ? error.message : 'The original Forge save could not be confirmed.', {
      kind: known?.kind ?? 'protocol', code: known?.code ?? 'frontier_save_unconfirmed',
      status: known?.status ?? 0, requestId: known?.requestId ?? null,
      retryable: known?.retryable ?? false,
    });
    this.name = 'ForgeEditError';
    this.preDispatch = preDispatch;
  }
}
function editInputError(message: string): ForgeEditError {
  return new ForgeEditError(new ChatClientError(message, {
    kind: 'validation', code: 'frontier_pre_dispatch', retryable: false,
  }), true);
}
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function sameEditAccount(token: string, epoch: number): void {
  if (getAuthToken() !== token || getAuthEpoch() !== epoch) throw new ForgeEditError(new ChatClientError(
    'Your account changed while the original save was pending. Its result was not applied to this workspace.',
    { kind: 'authorization', code: 'frontier_save_scope_changed', retryable: false }), false);
}
function checkedEditReceipt(value: unknown, projectId: string, source: string,
                            candidate: string, steps: readonly ForgeStep[], changed: boolean): boolean {
  if (!object(value) || value.schema !== 'skeleton.forge.frontier_authoring_batch.v1'
      || value.project_id !== projectId || value.source_sha256 !== source
      || value.candidate_sha256 !== candidate || value.persisted !== false
      || value.actually_changed !== changed || value.action_count !== steps.length
      || typeof value.receipt_sha256 !== 'string' || !SHA.test(value.receipt_sha256)
      || !Array.isArray(value.changes) || value.changes.length !== steps.length) return false;
  let before = source;
  for (const [index, item] of value.changes.entries()) {
    if (!object(item) || item.index !== index || item.operation !== steps[index].action
        || item.before_sha256 !== before || typeof item.after_sha256 !== 'string'
        || !SHA.test(item.after_sha256) || item.changed !== (before !== item.after_sha256)) return false;
    before = item.after_sha256;
  }
  return before === candidate;
}
function checkedEditSummary(value: unknown, projectId: string, candidate: string): boolean {
  return object(value) && value.schema === 'skeleton.forge.frontier_authoring_summary.v1'
    && value.project_id === projectId && value.source_sha256 === candidate && value.candidate_only === true
    && (!('native_engine_executed' in value) || value.native_engine_executed === false)
    && (!('release_certified' in value) || value.release_certified === false)
    && Array.isArray(value.layers) && value.layers.length <= 128
    && Array.isArray(value.action_catalog) && value.action_catalog.length === 500;
}

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
      || doc.recipe_catalog_count !== 4999999999500 || doc.catalog_total !== 5000000000000
      || doc.classic_recipe_count !== 4500 || doc.expanded_recipe_count !== 45000
      || doc.directed_recipe_count !== 450000 || doc.final_recipe_count !== 4500000 || doc.worldline_recipe_count !== 45000000 || doc.phase_recipe_count !== 450000000 || doc.campaign_recipe_count !== 4500000000 || doc.chronicle_recipe_count !== 45000000000 || doc.epoch_recipe_count !== 450000000000 || doc.continuity_recipe_count !== 4500000000000
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
  if (!Array.isArray(result.actions) || result.actions.length !== 500 || result.action_count !== 5000000000000)
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
  continuity?: string; continuity_index?: number; continuity_objective?: string;
  treatment: string; recipe_steps: string[]; source_index: number;
  style_index: number; actual_project_mutation: boolean;
};
export type ForgeRecipeResults = {
  schema: 'skeleton.forge.production_recipe_search.v1';
  total_catalog: number; matched: number; offset: number; limit: number;
  next_offset: number | null; domains: string[]; styles: string[];
  system_layers?: string[]; directors?: string[]; finishes?: string[];
  worldlines?: string[]; campaigns?: string[]; chronicles?: string[]; epochs?: string[]; continuities?: string[];
  items: ForgeRecipe[];
};
export async function searchForgeRecipes(query = '', domain = '', offset = 0,
                                         limit = 32, generation: 'classic' | 'expanded' | 'directed' | 'final' | 'worldline' | 'phase' | 'campaign' | 'chronicle' | 'epoch' | 'continuity' = 'classic',
                                         systemLayer = '', director = '', finish = '', worldline = '', phase = '', campaign = '', chronicle = '', epoch = '', continuity = ''): Promise<ForgeRecipeResults> {
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
    'continuity=' + encodeURIComponent(continuity),
    'domain=' + encodeURIComponent(domain),
    'offset=' + encodeURIComponent(String(offset)),
    'limit=' + encodeURIComponent(String(limit)),
  ].join('&');
  const results = await data(api.get<ForgeRecipeResults>(
    ROOT + '/recipes?' + params, options()), 'Could not search original-game production recipes.');
  if (!results || results.schema !== 'skeleton.forge.production_recipe_search.v1'
      || results.total_catalog !== (generation === 'continuity' ? 4500000000000 : generation === 'epoch' ? 450000000000 : generation === 'chronicle' ? 45000000000 : generation === 'campaign' ? 4500000000 : generation === 'phase' ? 450000000 : generation === 'worldline' ? 45000000 : generation === 'final' ? 4500000 : generation === 'directed' ? 450000 : generation === 'expanded' ? 45000 : 4500)
      || !Array.isArray(results.items)
      || results.items.length > 64
      || results.items.some(recipe => !(generation === 'classic' ? /^produce_[a-z_]+__[a-z_]+$/.test(recipe.operation)
          : generation === 'expanded' ? /^expand_[a-z_]+__[a-z_]+___[a-z_]+$/.test(recipe.operation)
          : generation === 'directed' ? /^direct_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+$/.test(recipe.operation)
          : generation === 'final' ? /^complete_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+$/.test(recipe.operation)
          : generation === 'worldline' ? /^worldline_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+$/.test(recipe.operation)
          : generation === 'phase' ? /^phase_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+$/.test(recipe.operation)
          : generation === 'continuity' ? /^continuity_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+___________[a-z_]+$/.test(recipe.operation)
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

export type ForgeContinuityRank = {
  rank: number; continuity: string; path: string; quality_score: number;
  quality_max: number; quality_kind: string; words: number; characters: number;
  bytes: number; content_sha256: string; criteria: Record<string, boolean>;
};
export type ForgeContinuityRanking = {
  schema: 'skeleton.forge.continuity_handbook_ranking.v1';
  sort: 'quality' | 'length';
  scope: 'ten_continuity_variants_for_one_exact_epoch_context';
  compared: 10; items: ForgeContinuityRank[];
};

export async function readForgeContinuityHandbook(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string, epoch: string,
  continuity: string,
): Promise<{markdown: string; score: number; words: number}> {
  const parts = [domain,treatment,director,worldline,phase,campaign,chronicle,epoch,continuity];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid continuity manuscript identity.');
  const book = await data(api.get<{schema: string; markdown: string;
    quality_score: number; content_sha256: string; words: number;
    covered_commands: number}>(
    ROOT+'/continuity-handbooks/'+parts.map(encodeURIComponent).join('/'),
    options()), 'Unable to render continuity manual.');
  if (book.schema !== 'skeleton.forge.continuity_handbook.v1'
      || !SHA.test(book.content_sha256) || book.covered_commands !== 5000
      || typeof book.markdown !== 'string' || book.markdown.length > 256000
      || !Number.isSafeInteger(book.words) || book.words < 1
      || !Number.isFinite(book.quality_score) || book.quality_score < 0
      || book.quality_score > 100)
    throw new Error('Continuity manuscript source validation failed.');
  return {markdown: book.markdown, score: book.quality_score, words: book.words};
}

export async function rankForgeContinuityHandbooks(
  domain: string, treatment: string, director: string, worldline: string,
  phase: string, campaign: string, chronicle: string, epoch: string,
  sort: 'quality' | 'length' = 'quality',
): Promise<ForgeContinuityRanking> {
  const parts = [domain,treatment,director,worldline,phase,campaign,chronicle,epoch];
  if (parts.some(part => !/^[a-z][a-z_]{0,40}$/.test(part)))
    throw new Error('Invalid scoped continuity ranking identity.');
  const ranked = await data(api.get<ForgeContinuityRanking>(
    ROOT+'/continuity-handbooks/rank/'+parts.map(encodeURIComponent).join('/')
      +'?sort='+sort, options()), 'Unable to rank continuity manuals.');
  if (!ranked || ranked.schema !== 'skeleton.forge.continuity_handbook_ranking.v1'
      || ranked.scope !== 'ten_continuity_variants_for_one_exact_epoch_context'
      || ranked.sort !== sort || ranked.compared !== 10
      || !Array.isArray(ranked.items) || ranked.items.length !== 10
      || ranked.items.some(item => !SHA.test(item.content_sha256)
        || !Number.isFinite(item.quality_score) || item.quality_score < 0
        || item.quality_score > 100 || !Number.isSafeInteger(item.words)
        || item.words < 1))
    throw new Error('Continuity document comparison contract invalid.');
  return ranked;
}

export async function copyForgeTiles(projectId: string, layer: string, x: number, y: number,
                                     width: number, height: number) {
  return data(api.post<{ tiles: number[]; palette: string[]; receipt_sha256: string }>(
    route(projectId) + '/tiles/copy', { layer, x, y, width, height },
    options()), 'Could not copy authored map region.');
}
function prepareForgeEdit(projectId: string, doc: ForgeDocument, steps: ForgeStep[], stableRequestKey?: string) {
  const original = cloneForgeEditInput(projectId, doc, steps);
  doc = original.document; steps = original.steps;
  verifyDoc(doc);
  if (doc.project_id !== projectId || doc.expected_version < 1) throw editInputError('Choose the current owned Forge source before saving.');
  if (!Array.isArray(steps) || steps.length < 1 || steps.length > 64) throw editInputError('Queue between one and 64 editor actions.');
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
          && /^phase_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+$/.test(step.action))
        && !(doc.campaign_recipe_count === 4500000000
          && /^campaign_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+$/.test(step.action))
        && !(doc.chronicle_recipe_count === 45000000000
          && /^chronicle_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+$/.test(step.action))
        && !(doc.continuity_recipe_count === 4500000000000
          && /^continuity_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+___________[a-z_]+$/.test(step.action))
        && !(doc.epoch_recipe_count === 450000000000
          && /^epoch_[a-z_]+__[a-z_]+___[a-z_]+____[a-z_]+_____[a-z_]+______[a-z_]+_______[a-z_]+________[a-z_]+_________[a-z_]+__________[a-z_]+$/.test(step.action)))) throw editInputError(
    'Select one or more supported editor operations.');
  const key = stableRequestKey ?? learningRequestKey('forge-author');
  if (typeof key !== 'string' || !key || key !== key.trim() || key.length > 512) throw editInputError('The original save identity is invalid.');
  encodeURIComponent(key);
  const body = { expected_version: doc.expected_version,
    expected_sha256: doc.source_sha256, idempotency_key: key, steps };
  return { key, body, path: route(projectId), projectId, source: doc.source_sha256,
           savedVersion: doc.expected_version + 1 };
}
export async function editForge(projectId: string, doc: ForgeDocument, steps: ForgeStep[],
                                preview: boolean, stableRequestKey?: string): Promise<ForgePreview | ForgeCommit> {
  let prepared: ReturnType<typeof prepareForgeEdit>;
  const loadingEpoch = getAuthEpoch();
  try {
    prepared = prepareForgeEdit(projectId, doc, steps, stableRequestKey);
    await initializeStoredToken();
    if (loadingEpoch !== getAuthEpoch() || !getAuthToken()) throw editInputError('Sign in to the same account before submitting the original save.');
  } catch (error) { throw error instanceof ForgeEditError ? error : new ForgeEditError(error, true); }
  const token = getAuthToken(), epoch = getAuthEpoch();
  let response: ApiResult<unknown>;
  try {
    response = preview
      ? await api.post<unknown>(prepared.path + '/edits/preview', prepared.body, options(prepared.key))
      : await api.patch<unknown>(prepared.path + '/edits', prepared.body, options(prepared.key));
  } catch (error) { throw new ForgeEditError(error, false); }
  sameEditAccount(token, epoch);
  if (!response.ok || response.data === null) {
    const payload = object(response.data) ? response.data : null;
    const detail = object(payload?.detail) ? payload.detail : payload;
    const proven = response.status >= 400 && response.status < 500 && detail?.code === 'frontier_pre_dispatch';
    throw new ForgeEditError(chatApiError(response, 'The original source save could not be confirmed.'), proven);
  }
  const value = response.data;
  const invalid = () => new ForgeEditError(new ChatClientError(
    'The original source receipt does not match this save. Refresh the saved source and retry the same original request.',
    { kind: 'protocol', code: 'frontier_save_unconfirmed', status: response.status, retryable: false }), false);
  if (!object(value)) throw invalid();
  const candidate = preview ? value.candidate_sha256 : value.source_sha256;
  if (typeof candidate !== 'string' || !SHA.test(candidate)
      || !checkedEditSummary(value.summary, prepared.projectId, candidate)
      || !checkedEditReceipt(value.batch_receipt, prepared.projectId, prepared.source,
                            candidate, prepared.body.steps, candidate !== prepared.source)
      || 'native_engine_executed' in value && value.native_engine_executed !== false
      || 'release_certified' in value && value.release_certified !== false) throw invalid();
  if (preview) {
    if (value.schema !== 'skeleton.game.frontier_studio_preview.v1' || value.persisted !== false
        || value.source_sha256 !== prepared.source) throw invalid();
    sameEditAccount(token, epoch);
    return value as unknown as ForgePreview;
  }
  if (value.schema !== 'skeleton.game.frontier_studio_committed.v1' || value.persisted !== true
      || value.project_id !== prepared.projectId || value.request_id !== prepared.key
      || value.original_source_sha256 !== prepared.source || candidate === prepared.source
      || value.expected_version !== prepared.savedVersion || !Number.isSafeInteger(value.head_version)
      || Number(value.head_version) < prepared.savedVersion || typeof value.replayed !== 'boolean'
      || typeof value.origin_request_digest !== 'string' || !SHA.test(value.origin_request_digest)) throw invalid();
  sameEditAccount(token, epoch);
  return value as unknown as ForgeCommit;
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
  if (!body || typeof body !== 'object' || Array.isArray(body)
      || Object.keys(body).length !== 3
      || !['layer_ids', 'connectors', 'itineraries'].every(key => Object.prototype.hasOwnProperty.call(body, key))
      || !Array.isArray(body.layer_ids) || body.layer_ids.length < 1 ||
      body.layer_ids.length > 8 || new Set(body.layer_ids).size !== body.layer_ids.length ||
      body.layer_ids.some(id => typeof id !== 'string' || !id || id.length > 128) ||
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
      && typeof value.sample_truncated === 'boolean'
      && (value.reachable ? Number.isSafeInteger(value.steps) && Number(value.steps) >= 1
          && SHA.test(String(value.path_sha256)) && value.sample.length >= 2
        : value.steps === null && value.path_sha256 === null && value.sample.length === 0)
      && value.sample.every(node =>
        Array.isArray(node) && node.length === 3 && typeof node[0] === 'string'
        && Number.isSafeInteger(node[1]) && Number.isSafeInteger(node[2]))
      && Number.isSafeInteger(value.transfers) && value.transfers >= 0
      && Array.isArray(value.connector_ids) && value.connector_ids.length === value.transfers
      && value.connector_ids.every(id => typeof id === 'string' && body.connectors.some(item => item.connector_id === id));
  if (!result || result.schema !== 'skeleton.forge.epic_interlayer_reference.v1'
      || result.project_id !== projectId || !SHA.test(result.project_sha256)
      || !SHA.test(result.receipt_sha256) || !Number.isSafeInteger(result.source_version) || result.source_version < 1
      || result.source_reference_only !== true
      || result.native_engine_executed !== false
      || result.transport_actions_applied !== false
      || result.release_certified !== false
      || result.verified_against_authoritative_source !== true
      || !Array.isArray(result.layer_ids) || !Array.isArray(result.connectors)
      || result.layer_ids.length !== body.layer_ids.length
      || result.layer_ids.some((id, index) => id !== body.layer_ids[index])
      || !result.layer_source_sha256 || typeof result.layer_source_sha256 !== 'object'
      || Object.keys(result.layer_source_sha256).length !== body.layer_ids.length
      || body.layer_ids.some(id => !SHA.test(result.layer_source_sha256[id]))
      || result.connectors.length !== body.connectors.length
      || result.connectors.some((item, index) => !object(item) || item.connector_id !== body.connectors[index].connector_id
          || item.mode !== body.connectors[index].mode || !Number.isFinite(item.distance_m) || item.distance_m < 0)
      || !Array.isArray(result.journeys)
      || result.journeys.length !== body.itineraries.length
      || result.journeys.some(item => !object(item))
      || result.journey_count !== body.itineraries.length
      || !Number.isSafeInteger(result.passed_count) || result.passed_count < 0
      || !Number.isSafeInteger(result.failed_count) || result.failed_count < 0
      || result.passed_count + result.failed_count !== result.journey_count
      || result.passed_count !== result.journeys.filter(j => j.passed === true).length
      || result.journeys.some((j, index) => typeof j.passed !== 'boolean'
          || j.journey_id !== body.itineraries[index].journey_id
          || j.require_alternate !== body.itineraries[index].require_alternate
          || JSON.stringify(j.start) !== JSON.stringify([body.itineraries[index].start.layer, body.itineraries[index].start.x, body.itineraries[index].start.y])
          || JSON.stringify(j.goal) !== JSON.stringify([body.itineraries[index].goal.layer, body.itineraries[index].goal.x, body.itineraries[index].goal.y])
          || !witness(j.primary)
          || (j.require_alternate ? !witness(j.alternate) : j.alternate !== null)
          || j.passed !== (j.primary.reachable && (!j.require_alternate || j.alternate?.reachable === true)))) {
    throw new ChatClientError('Epic multi-layer route report failed replay contract checks.',
      {kind: 'protocol', retryable: false});
  }
  return result;
}
