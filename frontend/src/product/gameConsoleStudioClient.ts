import { API_BASE } from '../../utils/apiBase';
import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { learningRequestKey, type LearningFile, type LearningProject, type LearningRequest } from './gameLearningClient';

export type ConsolePalette = { id: string; colors: string[] };
export type ConsoleTileset = { id: string; codec: string; palette_id: string; tiles: number[][]; bank?: number };
export type ConsoleCell = { tile: number; tileset_id: string; palette_id: string; flip_x: boolean; flip_y: boolean; collision: 'none' | 'solid' | 'one_way' | 'hazard' | 'goal' | 'water' };
export type ConsoleLayer = { id: string; width: number; height: number; cells: ConsoleCell[]; visible: boolean; offset: [number, number]; z: number };
export type ConsoleEntity = { id: string; kind: string; x: number; y: number; width: number; height: number; asset_id?: string | null; layer_id: string; properties: Record<string, unknown> };
export type ConsoleControls = { bindings: Record<string, string>; [key: string]: unknown };
export type ConsoleAsset = { id: string; kind: string; codec: string; data_base64: string; metadata: Record<string, unknown>; provenance: { kind: string; author_ref: string; [key: string]: unknown } };
export type ConsoleGraphNode = { id: string; parent_id: string | null; entity_id: string | null; x: number; y: number; visible: boolean; frames: { asset_id: string; x: number; y: number; width: number; height: number }[] };
export type ConsoleAnimation = { id: string; node_id: string; property: 'x' | 'y' | 'visible' | 'frame'; duration_ticks: number; loop: boolean; interpolation: 'step' | 'linear'; keyframes: { tick: number; value: number | boolean }[] };
export type ConsoleRule = { id: string; trigger: Record<string, unknown>; conditions: { source: 'variable' | 'metric'; key: string; op: 'eq' | 'ne' | 'lt' | 'le' | 'gt' | 'ge'; value: number }[]; actions: Record<string, unknown>[]; cooldown_ticks: number; once: boolean; enabled: boolean };
export type ConsoleSceneGraph = { schema_version: 'skeleton.console_scene_graph.v1'; project_id: string; tick_hz: 60; nodes: ConsoleGraphNode[]; animations: ConsoleAnimation[]; variables: { id: string; initial: number; min: number; max: number }[]; rules: ConsoleRule[] };
export type ConsoleDocument = {
  schema_version: 'skeleton.console_editor_project.v1'; project_id: string; title: string; target_id: string; profile_digest: string;
  viewport: { width: number; height: number }; tile_size: number; palettes: ConsolePalette[]; tilesets: ConsoleTileset[];
  layers: ConsoleLayer[]; entities: ConsoleEntity[]; controls: ConsoleControls; audio: { cues: Record<string, unknown>[] };
  config: Record<string, unknown>; assets: ConsoleAsset[];
};
export type ConsoleProfile = {
  target_id: string; label?: string; title?: string; family?: string; profile_digest?: string; digest?: string;
  viewport?: { width: number; height: number }; resolution?: { width: number; height: number } | number[];
  tile_codec?: string; palette_format?: string; codecs?: string[]; constraints?: Record<string, unknown>; native_constraints?: Record<string, unknown>; limits?: Record<string, number>;
  entity_kinds?: string[]; actions?: string[]; controller_actions?: string[]; sections?: string[]; config_ranges?: Record<string, [number, number]>; available_capabilities?: Record<string, boolean>; toolchain_readiness?: Record<string, unknown>; [key: string]: unknown;
};
export type ConsoleEdit = {
  op: 'set_scene_graph' | 'upsert_graph_node' | 'remove_graph_node' | 'upsert_animation' | 'remove_animation' | 'upsert_rule' | 'remove_rule' | 'upsert_variable' | 'remove_variable' | 'set_tile' | 'paint_tile' | 'set_palette' | 'upsert_tileset' | 'upsert_palette' | 'remove_tileset' | 'remove_palette' | 'transform_tile' | 'image_to_tiles' | 'bind_native_starter' | 'unbind_native_starter' | 'materialize_assets' | 'set_map_cell' | 'fill_map' | 'upsert_layer' | 'remove_layer' | 'upsert_entity' | 'remove_entity' | 'set_controls' | 'set_audio' | 'set_config' | 'put_asset' | 'delete_asset' | 'transform_asset' | 'replace_source';
  edit_id?: string; [key: string]: unknown;
};
export type NativeGraphCompatibility = { schema_version: 'skeleton.console_editor_native_graph.v1'; target_id: string; graph_digest: string; status: 'supported' | 'unsupported' | 'empty'; capabilities: string[]; limits: Record<string, number>; unsupported: { record_id: string | null; code: string; message: string }[]; native_data_bytes?: number; sprite_tile_count?: number; timeline_frames?: number; quantization?: unknown; measurement_scope: string };
export type ConsoleStudioDocument = { project: LearningProject; document: ConsoleDocument; profile: ConsoleProfile; manifest_digest: string; scene_graph?: ConsoleSceneGraph; native_graph_compatibility?: NativeGraphCompatibility; changes?: unknown[]; validation?: Record<string, unknown> };
export type ConsoleHandoff = {
  project_id: string; project_version: number; source_digest: string; target_id: string;
  build_handoff: { source_files: { path: string; sha256: string; bytes: number }[]; source_integration_required: boolean; native_execution_verified: false; materialized_source_files?: { path: string; sha256: string; bytes: number }[]; source_materialization_error?: { code: string; message: string } | null; native_binding?: { bound: boolean; code: string; message?: string; source_integration_required: boolean; deferred_mechanics?: string[] }; native_graph_compatibility?: NativeGraphCompatibility; [key: string]: unknown };
  source_handoff?: { status?: string; source_generation?: boolean; style_id?: string; supported_mechanics?: string[]; deferred_mechanics?: string[]; binary_compiled?: boolean; hardware_execution_verified?: boolean };
  toolchain: { status?: string; reason?: string; toolchain?: string; source_styles?: string[]; sdk_installed?: boolean | null; [key: string]: unknown };
};
const ROOT = '/api/game-console-studio';
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function id(value: string): string { if (!value || value.length > 128) invalid('The console project identity is invalid.'); return encodeURIComponent(value); }
async function request<T>(method: 'get' | 'post' | 'patch', path: string, body: unknown, input: LearningRequest = {}, key?: string): Promise<T> {
  const token = getAuthToken(); const options = { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 30000, idempotencyKey: key };
  const result: ApiResult<T> = await (method === 'get' ? api.get<T>(ROOT + path, options) : method === 'post' ? api.post<T>(ROOT + path, body, options) : api.patch<T>(ROOT + path, body, options));
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen the console project.', { kind: 'authorization', retryable: false });
  if (!result.ok || result.data === null) throw chatApiError(result, 'The console project could not be updated.'); return result.data;
}
function profile(value: ConsoleProfile): ConsoleProfile {
  if (!value || typeof value.target_id !== 'string' || !value.target_id || JSON.stringify(value).length > 131072) invalid('The console authoring profile is invalid.'); return value;
}
function document(value: ConsoleStudioDocument, projectId?: string): ConsoleStudioDocument {
  const doc = value?.document; const project = value?.project;
  if (!project || typeof project.project_id !== 'string' || projectId && project.project_id !== projectId || !Number.isSafeInteger(project.version) || project.version < 1
    || !Array.isArray(project.files) || project.files.length > 128 || !doc || doc.schema_version !== 'skeleton.console_editor_project.v1' || doc.project_id !== project.project_id
    || typeof doc.target_id !== 'string' || !/^[a-f0-9]{64}$/.test(doc.profile_digest) || !/^[a-f0-9]{64}$/.test(value.manifest_digest)
    || !Array.isArray(doc.palettes) || doc.palettes.length > 256 || !Array.isArray(doc.tilesets) || doc.tilesets.length > 64
    || !Array.isArray(doc.layers) || doc.layers.length > 8 || !Array.isArray(doc.entities) || doc.entities.length > 256 || !Array.isArray(doc.assets) || doc.assets.length > 256
    || !Number.isSafeInteger(doc.tile_size) || doc.tile_size < 1 || doc.tile_size > 64 || !doc.viewport || !Number.isSafeInteger(doc.viewport.width) || !Number.isSafeInteger(doc.viewport.height)
    || doc.viewport.width < 1 || doc.viewport.height < 1 || doc.viewport.width > 4096 || doc.viewport.height > 4096 || JSON.stringify(doc).length > 4 * 1024 * 1024) invalid('The console project returned an invalid authoring document.');
  for (const palette of doc.palettes) if (!palette || typeof palette.id !== 'string' || !Array.isArray(palette.colors) || palette.colors.length > 256 || palette.colors.some(color => !/^#[a-f0-9]{6}([a-f0-9]{2})?$/i.test(color))) invalid('The console palette is invalid.');
  for (const tileset of doc.tilesets) if (!tileset || typeof tileset.id !== 'string' || !Array.isArray(tileset.tiles) || tileset.tiles.length > 2048 || tileset.tiles.some(tile => !Array.isArray(tile) || tile.length !== 64 || tile.some(pixel => !Number.isSafeInteger(pixel) || pixel < 0 || pixel > 255))) invalid('The native tile data is invalid.');
  for (const layer of doc.layers) if (!layer || typeof layer.id !== 'string' || !Number.isSafeInteger(layer.width) || !Number.isSafeInteger(layer.height) || layer.width < 1 || layer.height < 1 || layer.width * layer.height > 65536 || !Array.isArray(layer.cells) || layer.cells.length !== layer.width * layer.height) invalid('The authored map is invalid.');
  const graph = value.scene_graph; if (graph && (graph.schema_version !== 'skeleton.console_scene_graph.v1' || graph.project_id !== doc.project_id || graph.tick_hz !== 60 || !Array.isArray(graph.nodes) || graph.nodes.length > 256 || !Array.isArray(graph.animations) || graph.animations.length > 128 || !Array.isArray(graph.variables) || graph.variables.length > 32 || !Array.isArray(graph.rules) || graph.rules.length > 64 || JSON.stringify(graph).length > 512 * 1024)) invalid('The scene graph does not match the current authoring project.');
  const native = value.native_graph_compatibility;
  if (native && (native.schema_version !== 'skeleton.console_editor_native_graph.v1' || native.target_id !== doc.target_id || !/^[a-f0-9]{64}$/.test(native.graph_digest) || !['supported', 'unsupported', 'empty'].includes(native.status) || !Array.isArray(native.capabilities) || native.capabilities.length > 64 || !Array.isArray(native.unsupported) || native.unsupported.length > 512 || native.unsupported.some(issue => !issue || typeof issue.code !== 'string' || typeof issue.message !== 'string' || issue.record_id !== null && typeof issue.record_id !== 'string') || JSON.stringify(native).length > 512 * 1024)) invalid('The native graph compatibility does not match the saved project.');
  profile(value.profile); if (value.profile.profile_digest !== doc.profile_digest || value.profile.target_id !== doc.target_id) invalid('The console profile does not match the saved document.'); return value;
}
export async function getConsoleStudioProfiles(input: LearningRequest = {}): Promise<ConsoleProfile[]> {
  const result = await request<{ profiles: ConsoleProfile[] }>('get', '/profiles', null, input);
  if (!Array.isArray(result.profiles) || result.profiles.length > 512) invalid('The console authoring catalogue exceeds its bounds.'); return result.profiles.map(profile);
}
export async function createConsoleStudioProject(targetId: string, title: string, seed: number, input: LearningRequest = {}, key = learningRequestKey('console-create')): Promise<ConsoleStudioDocument> {
  return document(await request<ConsoleStudioDocument>('post', '/projects', { target_id: targetId, title, seed, idempotency_key: key }, input, key));
}
export async function getConsoleStudioDocument(projectId: string, input: LearningRequest = {}): Promise<ConsoleStudioDocument> {
  return document(await request<ConsoleStudioDocument>('get', '/projects/' + id(projectId) + '/document', null, input), projectId);
}
export async function saveConsoleStudioDocument(current: ConsoleStudioDocument, edits: ConsoleEdit[], input: LearningRequest = {}, key = learningRequestKey('console-edit')): Promise<ConsoleStudioDocument> {
  if (!edits.length || edits.length > 128) throw new Error('Save no more than 128 authored changes at a time.');
  return document(await request<ConsoleStudioDocument>('patch', '/projects/' + id(current.project.project_id) + '/document', { expected_version: current.project.version, expected_manifest_digest: current.manifest_digest, idempotency_key: key, edits }, input, key), current.project.project_id);
}
export async function getConsoleStudioHandoff(projectId: string, input: LearningRequest = {}): Promise<ConsoleHandoff> {
  const result = await request<ConsoleHandoff>('get', '/projects/' + id(projectId) + '/handoff', null, input);
  const handoff = result?.build_handoff;
  if (result?.project_id !== projectId || !Number.isSafeInteger(result.project_version) || result.project_version < 1 || typeof result.target_id !== 'string' || !/^[a-f0-9]{64}$/.test(result.source_digest) || !handoff || handoff.native_execution_verified !== false || typeof handoff.source_integration_required !== 'boolean' || !Array.isArray(handoff.source_files) || handoff.source_files.length > 128 || handoff.source_files.some(file => typeof file.path !== 'string' || !/^[a-f0-9]{64}$/.test(file.sha256) || !Number.isSafeInteger(file.bytes) || file.bytes < 0) || !result.toolchain || JSON.stringify(result).length > 512 * 1024) invalid('The console build handoff is invalid.');
  if (handoff.native_binding && (typeof handoff.native_binding.bound !== 'boolean' || typeof handoff.native_binding.source_integration_required !== 'boolean' || typeof handoff.native_binding.code !== 'string')) invalid('The native source binding receipt is invalid.');
  return result;
}
export function consoleFiles(current: ConsoleStudioDocument): LearningFile[] { return current.project.files || []; }

export type StudioReviewProposal = { operation: string; payload: Record<string, unknown>; finding_id: string; reason: string; source_request_digest: string; source_identity: Record<string, unknown>; requires_explicit_execution: true; automatic_execution: false; proposal_digest: string };
export type StudioReviewFinding = { finding_id?: string; severity: string; code: string; message: string; evidence_refs: string[]; measurement?: unknown; candidate_constraint?: unknown; classification?: string };
export type StudioReviewComparison = { status: 'paired_observation' | 'inconclusive'; comparability_failures: string[]; measurements: { metric: string; baseline: number | null; candidate: number | null; delta: number | null; preferred_direction: string; bounded_regression_observed: boolean; advisory?: boolean }[]; observed_regressions: string[]; next_action: string; baseline_job_id: string; comparison_digest: string };
export type StudioReview = { comparison?: StudioReviewComparison; triangle_review?: { roles: Record<string, unknown>; priority_findings: StudioReviewFinding[]; triangle_digest: string }; review_digest: string; frames: { evidence_ref: string; thumbnail?: Record<string, unknown>; [key: string]: unknown }[]; findings: StudioReviewFinding[]; metrics?: Record<string, unknown>; execution?: Record<string, unknown>; unavailable?: unknown; semantic_review?: { scope?: string; layout?: Record<string, unknown>; control_response?: Record<string, unknown>; actual_events?: unknown; observed_success_steps?: number[]; findings?: StudioReviewFinding[]; remedial_actions?: StudioReviewProposal[]; semantic_digest?: string }; remedial_actions?: StudioReviewProposal[]; [key: string]: unknown };
export async function startStudioReview(current: LearningProject, config: { seed: number; episodeSteps: number; captureEvery: number; sourceId?: string; actions?: string[]; policyId?: string; baselineReviewJobId?: string }, input: LearningRequest = {}, key = learningRequestKey('studio-review')) {
  const token = getAuthToken(); const result = await api.post<{ job: import('./gameLearningClient').LearningJob }>('/api/game-learning/projects/' + id(current.project_id) + '/review', { expected_version: current.version, idempotency_key: key, seed: config.seed, episode_steps: config.episodeSteps, capture_every: config.captureEvery, source_id: config.sourceId, actions: config.actions, policy_id: config.policyId, baseline_review_job_id: config.baselineReviewJobId }, { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 30000, idempotencyKey: key });
  if (token !== getAuthToken()) invalid('Your account changed during the review request.'); if (!result.ok || !result.data) throw chatApiError(result, 'The measured studio review could not start.'); if (result.data.job?.project_id !== current.project_id) invalid('The review belongs to a different project.'); return result.data.job;
}
export async function getStudioReview(projectId: string, jobId: string, input: LearningRequest = {}): Promise<{ job: import('./gameLearningClient').LearningJob; review: StudioReview }> {
  const token = getAuthToken(); const result = await api.get<{ job: import('./gameLearningClient').LearningJob; review: StudioReview }>('/api/game-learning/projects/' + id(projectId) + '/reviews/' + id(jobId), { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 30000 });
  if (token !== getAuthToken()) invalid('Your account changed while opening a review.'); if (!result.ok || !result.data) throw chatApiError(result, 'The measured studio review could not be read.'); const value = result.data;
  if (value.job?.job_id !== jobId || value.job.project_id !== projectId || !value.review || !Array.isArray(value.review.frames) || value.review.frames.length > 512 || !Array.isArray(value.review.findings) || value.review.findings.length > 256 || !/^[a-f0-9]{64}$/.test(value.review.review_digest) || JSON.stringify(value.review).length > 8 * 1024 * 1024) invalid('The returned studio review exceeds its evidence bounds.'); return value;
}
export async function executeStudioReviewProposal(project: LearningProject, proposal: StudioReviewProposal, input: LearningRequest = {}) {
  if (!['console.inspect', 'console.edit'].includes(proposal.operation) || proposal.requires_explicit_execution !== true || proposal.automatic_execution !== false || proposal.source_identity.project_id !== project.project_id || !/^[a-f0-9]{64}$/.test(proposal.proposal_digest)) invalid('This measured review proposal cannot be executed here.');
  if (proposal.operation === 'console.edit' && (proposal.source_identity.project_version !== project.version || proposal.payload.expected_version !== project.version || !/^[a-f0-9]{64}$/.test(String(proposal.payload.expected_manifest_digest)) || typeof proposal.payload.idempotency_key !== 'string')) throw new Error('The shared project changed after this review. Run a new review before applying its draft.');
  const token = getAuthToken(); const key = typeof proposal.payload.idempotency_key === 'string' ? proposal.payload.idempotency_key : learningRequestKey('review-inspect');
  const result = await api.post<{ schema_version: string; project_id: string; operation: string; command_digest: string; result_digest: string; result: Record<string, unknown> }>('/api/game-studio-tools/execute', { operation: proposal.operation, project_id: project.project_id, payload: proposal.payload }, { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 30000, idempotencyKey: key });
  if (token !== getAuthToken()) invalid('Your account changed during the scoped review action.'); if (!result.ok || !result.data) throw chatApiError(result, 'The selected review action could not be completed.');
  const value = result.data; if (value.schema_version !== 'skeleton.game.studio_tool_receipt.v1' || value.project_id !== project.project_id || value.operation !== proposal.operation || !/^[a-f0-9]{64}$/.test(value.command_digest) || !/^[a-f0-9]{64}$/.test(value.result_digest) || !value.result || JSON.stringify(value).length > 2 * 1024 * 1024) invalid('The scoped review action returned an invalid receipt.'); return value;
}

export async function exportStudioReview(projectId: string, jobId: string, input: LearningRequest = {}) {
  const token = getAuthToken(); const controller = new AbortController(); const abort = () => controller.abort(); const timer = setTimeout(abort, 30000); input.signal?.addEventListener('abort', abort, { once: true }); if (input.signal?.aborted) abort();
  try {
    const response = await fetch(API_BASE + '/api/game-learning/projects/' + id(projectId) + '/reviews/' + id(jobId) + '/export', { headers: authHeaders(), signal: controller.signal });
    if (!response.ok) throw new Error('The review export is unavailable under the current source permissions.');
    const hash = response.headers.get('X-Content-SHA256'); if (!hash || !/^[a-f0-9]{64}$/.test(hash) || !response.headers.get('content-type')?.startsWith('application/json')) invalid('The review export has no verified content identity.');
    const chunks: Uint8Array[] = []; let size = 0;
    if (response.body?.getReader) { const reader = response.body.getReader(); try { for (;;) { const row = await reader.read(); if (row.done) break; size += row.value.byteLength; if (size > 8 * 1024 * 1024) invalid('The review export exceeds its byte limit.'); chunks.push(row.value); } } finally { await reader.cancel().catch(() => undefined); } }
    else { const length = Number(response.headers.get('content-length')); if (!length || length > 8 * 1024 * 1024) invalid('This device requires a bounded review export size.'); const bytes = new Uint8Array(await response.arrayBuffer()); if (bytes.byteLength !== length) invalid('The review export size changed.'); chunks.push(bytes); size = bytes.byteLength; }
    const bytes = new Uint8Array(size); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; } const content = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, content) !== hash || token !== getAuthToken() || input.signal?.aborted) invalid('The review export content or account changed.');
    return { filename: 'studio-review-' + hash.slice(0, 16) + '.json', mimeType: 'application/json', content, contentDigest: hash };
  } finally { clearTimeout(timer); input.signal?.removeEventListener('abort', abort); }
}
