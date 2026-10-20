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
  action_catalog: string[]; already_saved: boolean;
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
      || !Array.isArray(doc.action_catalog) || doc.action_catalog.length !== 150
      || !Array.isArray(doc.layers) || doc.layers.length > 128) {
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
  if (!Array.isArray(result.actions) || result.actions.length !== 150 || result.action_count !== 150)
    throw new Error('Forge Studio action catalogue is incomplete.');
  return result.actions;
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
      steps.some(step => !doc.action_catalog.includes(step.action))) throw new Error(
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
