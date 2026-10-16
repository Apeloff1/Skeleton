import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { learningRequestKey, type LearningProject, type LearningRequest } from './gameLearningClient';

const ROOT = '/api/game-learning';
export type GamePlay = {
  play_id: string; project_id: string; status: string; control_version: number;
  controller: 'human' | 'ai' | 'replay'; controller_epoch: number; stream_id: string; frame_sequence: number; actions: string[];
  control_token?: string; input_version: number; latest_frame?: Record<string, unknown> | null;
  observation?: Record<string, unknown>; steps: number; reward: number; recording_id?: string | null;
  keyboard_bindings?: Record<string, string> | null; policy_id?: string | null; source_id?: string | null; input_epoch?: number;
  capabilities?: { held_buttons?: boolean; keyboard?: boolean; gamepad?: boolean; max_fps?: number; input_mode?: string; idle_advances_environment?: boolean };
  error?: string | null; resume_available?: boolean;
};
export type GameRecording = {
  recording_id: string; play_id: string; project_id: string; status: string; label?: string;
  step_count?: number; steps?: number; duration_seconds?: number; action_count?: number;
  feedback?: { rating?: number; note?: string }; usable_for_training?: boolean;
  consent?: boolean; created_at?: string; updated_at?: string; source_id?: string;
  environment?: { max_episode_steps: number; [key: string]: unknown }; summary?: Record<string, unknown>; [key: string]: unknown;
};
export type GameTrainingInstance = {
  instance_id: string; job_id?: string; worker?: number; status: string;
  frame_sequence: number; latest_frame?: Record<string, unknown> | null;
  observation?: Record<string, unknown>; steps?: number; reward?: number; episode?: number;
  metrics?: Record<string, unknown>; task?: string; resource?: string; [key: string]: unknown;
};
export type GameTrainingInstances = { job_id: string; instances: GameTrainingInstance[]; status?: string; stream_id?: string };
export type GameResourceProfile = { profile_id: string; label: string; max_training_workers: number; max_live_plays: number; host_cpu_count?: number; effective_cpu_count?: number; memory_limit_bytes?: number; available?: boolean; readiness?: { code: string; message: string }; combined_instance_capacity?: number; shared_single_capacity?: boolean; global_actor_safety_ceiling?: number; instance_memory_allowance_bytes?: number; capacity_scope?: string };
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function identity(value: string): string { if (!value || value.length > 128) invalid('The game session identity is invalid.'); return encodeURIComponent(value); }
async function request<T>(method: 'get' | 'post', path: string, body: unknown, input: LearningRequest = {}, key?: string): Promise<T> {
  const token = getAuthToken();
  const options = { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 15000, idempotencyKey: key };
  const result: ApiResult<T> = await (method === 'get' ? api.get<T>(ROOT + path, options) : api.post<T>(ROOT + path, body, options));
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen the game session.', { kind: 'authorization', retryable: false });
  if (!result.ok || result.data === null) throw chatApiError(result, 'The game session could not be updated.');
  return result.data;
}
function frame(value: unknown): void {
  if (value == null) return;
  if (typeof value !== 'object' || Array.isArray(value) || JSON.stringify(value).length > 3 * 1024 * 1024) invalid('The returned game frame exceeds the preview bounds.');
}
export function validateGamePlay(value: GamePlay, projectId?: string, playId?: string): GamePlay {
  if (!value || typeof value.play_id !== 'string' || !value.play_id || typeof value.project_id !== 'string'
    || projectId && value.project_id !== projectId || playId && value.play_id !== playId
    || typeof value.status !== 'string' || !['human', 'ai', 'replay'].includes(value.controller)
    || typeof value.stream_id !== 'string' || !value.stream_id || !Number.isSafeInteger(value.frame_sequence) || value.frame_sequence < 0
    || !Number.isSafeInteger(value.controller_epoch) || value.controller_epoch < 1 || !Number.isSafeInteger(value.control_version) || value.control_version < 1 || !Number.isSafeInteger(value.input_version) || value.input_version < 0
    || value.actions !== undefined && (!Array.isArray(value.actions) || value.actions.length > 128 || value.actions.some(action => typeof action !== 'string' || action.length > 100))
    || !Number.isSafeInteger(value.steps) || value.steps < 0 || !Number.isFinite(value.reward)
    || value.control_token !== undefined && (typeof value.control_token !== 'string' || value.control_token.length > 512)) invalid('The server returned an invalid play session.');
  if (value.capabilities && (value.capabilities.held_buttons !== undefined && typeof value.capabilities.held_buttons !== 'boolean' || value.capabilities.idle_advances_environment !== undefined && typeof value.capabilities.idle_advances_environment !== 'boolean' || value.capabilities.input_mode !== undefined && (typeof value.capabilities.input_mode !== 'string' || value.capabilities.input_mode.length > 80))) invalid('The game input capabilities are invalid.');
  frame(value.latest_frame); return { ...value, actions: value.actions || [] };
}
export async function startGamePlay(project: LearningProject, config: { sourceId?: string; seed: number; controller: 'human' | 'ai'; policyId?: string; fps?: number; maxSteps?: number }, input: LearningRequest = {}, key = learningRequestKey('play')): Promise<GamePlay> {
  const result = await request<{ play: GamePlay }>('post', '/projects/' + identity(project.project_id) + '/play', {
    expected_version: project.version, idempotency_key: key, source_id: config.sourceId,
    seed: config.seed, controller: config.controller, policy_id: config.policyId, fps: config.fps || 15, max_steps: config.maxSteps || 4096,
  }, input, key);
  return validateGamePlay(result.play, project.project_id);
}
export async function getGamePlay(playId: string, input: LearningRequest = {}): Promise<GamePlay> {
  const result = await request<{ play: GamePlay }>('get', '/play/' + identity(playId), null, input);
  return validateGamePlay(result.play, undefined, playId);
}
export async function inputGamePlay(play: GamePlay, action: string, held: boolean, sequence: number, input: LearningRequest = {}): Promise<GamePlay> {
  if (!play.control_token || play.controller !== 'human' || !play.actions.includes(action)) throw new Error('Take control of this session before sending a supported action.');
  const result = await request<{ play: GamePlay }>('post', '/play/' + identity(play.play_id) + '/input', {
    control_token: play.control_token, expected_control_version: play.control_version,
    input_sequence: sequence, action, held,
  }, input);
  return validateGamePlay(result.play, play.project_id, play.play_id);
}
export async function controlGamePlay(play: GamePlay, action: 'pause' | 'resume' | 'stop' | 'takeover' | 'reset', config: { controller?: 'human' | 'ai'; policyId?: string } = {}, input: LearningRequest = {}): Promise<GamePlay> {
  const result = await request<{ play: GamePlay }>('post', '/play/' + identity(play.play_id) + '/control', {
    expected_control_version: play.control_version, action, controller: config.controller, policy_id: config.policyId,
  }, input);
  return validateGamePlay(result.play, play.project_id, play.play_id);
}
function recording(value: GameRecording, projectId?: string): GameRecording {
  if (!value || typeof value.recording_id !== 'string' || !value.recording_id || typeof value.play_id !== 'string'
    || typeof value.project_id !== 'string' || projectId && value.project_id !== projectId || typeof value.status !== 'string') invalid('The server returned an invalid demonstration.');
  return value;
}
export async function startGameRecording(play: GamePlay, label: string, input: LearningRequest = {}, key = learningRequestKey('recording')): Promise<GameRecording> {
  const result = await request<{ recording: GameRecording }>('post', '/play/' + identity(play.play_id) + '/recordings', {
    expected_control_version: play.control_version, consent: true, label: label.trim() || undefined, idempotency_key: key,
  }, input, key);
  return recording(result.recording, play.project_id);
}
export async function stopGameRecording(current: GameRecording, feedback: { rating?: number; note?: string }, input: LearningRequest = {}): Promise<GameRecording> {
  const result = await request<{ recording: GameRecording }>('post', '/recordings/' + identity(current.recording_id) + '/stop', {
    consent: true, feedback: feedback.rating ? { rating: feedback.rating, note: feedback.note?.trim() || undefined } : undefined,
  }, input);
  return recording(result.recording, current.project_id);
}
export async function getGameRecording(id: string, input: LearningRequest = {}): Promise<GameRecording> {
  const result = await request<{ recording: GameRecording }>('get', '/recordings/' + identity(id), null, input);
  const value = recording(result.recording); if (value.recording_id !== id) invalid('A different demonstration was returned.'); return value;
}
export async function replayGameRecording(current: LearningProject, id: string, input: LearningRequest = {}, key = learningRequestKey('replay')): Promise<GamePlay> {
  const result = await request<{ play: GamePlay }>('post', '/recordings/' + identity(id) + '/replay', { expected_version: current.version, idempotency_key: key, fps: 15 }, input, key);
  return validateGamePlay(result.play);
}
export async function listGameRecordings(projectId: string, input: LearningRequest = {}): Promise<GameRecording[]> {
  const result = await request<{ recordings: GameRecording[] }>('get', '/projects/' + identity(projectId) + '/recordings', null, input);
  if (!Array.isArray(result.recordings) || result.recordings.length > 128) invalid('The demonstration list exceeds its bounds.');
  return result.recordings.map(value => recording(value, projectId));
}
export async function getGameTrainingInstances(jobId: string, input: LearningRequest = {}): Promise<GameTrainingInstances> {
  const result = await request<GameTrainingInstances>('get', '/jobs/' + identity(jobId) + '/instances', null, input);
  if (result.job_id !== jobId || !Array.isArray(result.instances) || result.instances.length > 8) invalid('The worker view returned an invalid job identity.');
  const ids = new Set<string>();
  for (const value of result.instances) {
    if (!value || typeof value.instance_id !== 'string' || ids.has(value.instance_id) || typeof value.status !== 'string'
      || !Number.isSafeInteger(value.frame_sequence) || value.frame_sequence < 0 || value.job_id && value.job_id !== jobId) invalid('The worker view returned an invalid instance.');
    ids.add(value.instance_id); frame(value.latest_frame);
  }
  return result;
}

export async function getGameResources(input: LearningRequest = {}): Promise<{ profiles: GameResourceProfile[]; gpu_available: boolean }> {
  const result = await request<{ profiles: GameResourceProfile[]; gpu_available: boolean }>('get', '/resources', null, input);
  if (!Array.isArray(result.profiles) || result.profiles.length > 16 || typeof result.gpu_available !== 'boolean') invalid('The compute resource catalogue is invalid.');
  for (const profile of result.profiles) {
    if (!profile || typeof profile.profile_id !== 'string' || typeof profile.label !== 'string' || !Number.isSafeInteger(profile.max_training_workers) || profile.max_training_workers < 0 || profile.max_training_workers > 8 || !Number.isSafeInteger(profile.max_live_plays) || profile.max_live_plays < 0 || profile.max_live_plays > 4 || profile.available !== undefined && typeof profile.available !== 'boolean') invalid('The compute resource profile is invalid.');
    if (profile.available === false) { if (profile.max_training_workers !== 0 || profile.max_live_plays !== 0 || profile.combined_instance_capacity !== 0) invalid('Unavailable compute must have zero admitted capacity.'); }
    else if (profile.max_training_workers < 1 || profile.max_live_plays < 1 || profile.combined_instance_capacity === 0) invalid('Zero compute capacity requires an explicit unavailable profile.');
    if (profile.combined_instance_capacity !== undefined && (!Number.isSafeInteger(profile.combined_instance_capacity) || profile.combined_instance_capacity < 0 || profile.combined_instance_capacity > 12)) invalid('The combined instance capacity is invalid.');
  }
  return result;
}

export async function listGamePlays(projectId: string, input: LearningRequest = {}): Promise<GamePlay[]> {
  const result = await request<{ plays: GamePlay[] }>('get', '/projects/' + identity(projectId) + '/play', null, input);
  if (!Array.isArray(result.plays) || result.plays.length > 32) invalid('The play session list exceeds its bounds.');
  return result.plays.map(value => validateGamePlay(value, projectId));
}

export async function exportGameRecording(id: string, input: LearningRequest = {}): Promise<{ filename: string; mimeType: string; content: string }> {
  const token = getAuthToken();
  const result = await request<{ recording_id: string; filename: string; media_type: string; content: string; content_digest: string }>('get', '/recordings/' + identity(id) + '/export', null, input);
  if (result.recording_id !== id || typeof result.filename !== 'string' || result.filename.includes('/') || result.filename.includes('\\') || result.media_type !== 'application/json' || typeof result.content !== 'string' || new TextEncoder().encode(result.content).byteLength > 2 * 1024 * 1024 || !/^[a-f0-9]{64}$/.test(result.content_digest)) invalid('The demonstration export is invalid.');
  if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, result.content) !== result.content_digest || token !== getAuthToken() || input.signal?.aborted) invalid('The demonstration export failed its content or account check.');
  return { filename: result.filename, mimeType: result.media_type, content: result.content };
}
export async function withdrawGameRecording(current: GameRecording, input: LearningRequest = {}): Promise<GameRecording> {
  const result = await request<{ recording: GameRecording }>('post', '/recordings/' + identity(current.recording_id) + '/stop', { consent: false }, input);
  return recording(result.recording, current.project_id);
}
