import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { learningRequestKey, type ConsoleBuildArtifact, type LearningJob, type LearningProject, type LearningRequest, type LearningSource } from './gameLearningClient';
import { validateGamePlay, type GamePlay } from './gamePlayClient';
import { type CampaignConfig, type StudioCampaign } from './gameStudioLearningClient';

export type CompiledRomPlayback = {
  artifact_id: string; project_id: string; project_version: number; target_id: string;
  artifact_digest: string; source_id?: string | null; available: boolean;
  readiness: { code?: string; message?: string; [key: string]: unknown } | string;
  core?: Record<string, unknown> | null; source_kind: 'build_artifact'; execution_kind: 'libretro';
  native_instrumentation?: { available: boolean; layout_digest?: string | null; fields?: string[]; descriptor_digest?: string; core_ids?: string[]; reward_components?: string[]; game_success_available?: boolean; measurement_scope?: string; reason?: string };
};
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function path(projectId: string, artifactId: string) { if (!projectId || !artifactId || projectId.length > 128 || artifactId.length > 128) invalid('The compiled game identity is invalid.'); return '/api/game-learning/projects/' + encodeURIComponent(projectId) + '/build-artifacts/' + encodeURIComponent(artifactId); }
async function request<T>(method: 'get' | 'post', route: string, body: unknown, input: LearningRequest = {}, key?: string): Promise<T> {
  const token = getAuthToken(); const options = { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 30000, idempotencyKey: key };
  const result: ApiResult<T> = await (method === 'get' ? api.get<T>(route, options) : api.post<T>(route, body, options));
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen the compiled game.', { kind: 'authorization', retryable: false });
  if (!result.ok || result.data === null) throw chatApiError(result, 'The compiled game could not be opened.'); return result.data;
}
function playback(value: CompiledRomPlayback, projectId: string, artifact: ConsoleBuildArtifact) {
  const signals = value?.native_instrumentation; if (signals && (typeof signals.available !== 'boolean' || !Array.isArray(signals.fields) || signals.fields.length > 32 || signals.fields.some(field => typeof field !== 'string') || signals.available && (!/^[a-f0-9]{64}$/.test(signals.layout_digest || '') || !/^[a-f0-9]{64}$/.test(signals.descriptor_digest || '') || signals.game_success_available !== true))) invalid('The native instrumentation evidence is invalid.');
  if (!value || value.project_id !== projectId || value.artifact_id !== artifact.artifact_id || value.artifact_digest !== artifact.digest || !Number.isSafeInteger(value.project_version) || typeof value.available !== 'boolean' || typeof value.target_id !== 'string' || value.source_kind !== 'build_artifact' || value.execution_kind !== 'libretro' || JSON.stringify(value).length > 131072) invalid('The compiled game playback evidence differs from its build.'); return value;
}
export async function getCompiledRomPlayback(projectId: string, artifact: ConsoleBuildArtifact, input: LearningRequest = {}): Promise<CompiledRomPlayback> { const result = await request<{ playback: CompiledRomPlayback }>('get', path(projectId, artifact.artifact_id) + '/playback', null, input); return playback(result.playback, projectId, artifact); }
export async function admitCompiledRom(project: LearningProject, artifact: ConsoleBuildArtifact, input: LearningRequest = {}, key = learningRequestKey('compiled-rom-admit')) { const result = await request<{ project: LearningProject; source: LearningSource; playback: CompiledRomPlayback }>('post', path(project.project_id, artifact.artifact_id) + '/admit', { expected_version: project.version, idempotency_key: key }, input, key); if (result.project?.project_id !== project.project_id || !result.source?.source_id) invalid('The compiled source belongs to a different project.'); playback(result.playback, project.project_id, artifact); return result; }
export async function playCompiledRom(project: LearningProject, artifact: ConsoleBuildArtifact, config: { seed: number; controller: 'human' | 'ai'; policyId?: string }, input: LearningRequest = {}, key = learningRequestKey('compiled-rom-play')) { const result = await request<{ play: GamePlay; project?: LearningProject }>('post', path(project.project_id, artifact.artifact_id) + '/play', { expected_version: project.version, idempotency_key: key, seed: config.seed, controller: config.controller, policy_id: config.policyId, fps: 15, max_steps: 4096 }, input, key); return { ...result, play: validateGamePlay(result.play, project.project_id) }; }
export async function trainCompiledRom(project: LearningProject, artifact: ConsoleBuildArtifact, config: { epochs: number; episodeSteps: number; workers: number; seed: number }, input: LearningRequest = {}, key = learningRequestKey('compiled-rom-train')) { const result = await request<{ job: LearningJob; project?: LearningProject }>('post', path(project.project_id, artifact.artifact_id) + '/train', { expected_version: project.version, idempotency_key: key, algorithm: 'q_learning', epochs: config.epochs, episode_steps: config.episodeSteps, workers: config.workers, seed: config.seed, fresh_policy: true, resource_profile: 'cpu', session_ids: [], demonstration_ids: [] }, input, key); if (!result.job || result.job.project_id !== project.project_id || typeof result.job.job_id !== 'string') invalid('The compiled game training job belongs to a different project.'); return result; }
export async function campaignCompiledRom(project: LearningProject, artifact: ConsoleBuildArtifact, config: CampaignConfig, input: LearningRequest = {}, key = learningRequestKey('compiled-rom-campaign')) {
  if (config.sourceId) throw new Error('The compiled campaign source is derived from this exact build.');
  const result = await request<{ campaign: StudioCampaign; source: LearningSource; playback: CompiledRomPlayback }>('post', path(project.project_id, artifact.artifact_id) + '/campaign', {
    expected_version: project.version, idempotency_key: key, round_limit: config.roundLimit, slice_rounds: config.sliceRounds, episodes: config.episodes, max_steps: config.maxSteps, seed: config.seed,
    policy_id: config.policyId, auto_continue: config.autoContinue ?? false, authorization_seconds: config.authorizationSeconds ?? 21600, evaluation_seeds: config.evaluationSeeds ?? 3,
    curriculum: config.curriculum ?? 'mixed', objective_weights: config.objectiveWeights, max_mean_step_ms: config.maxMeanStepMs ?? null, max_death_regression: config.maxDeathRegression ?? 0, max_worst_seed_regression: config.maxWorstSeedRegression ?? 0, proposal_width: config.proposalWidth ?? 2, exploration_strategy: config.explorationStrategy ?? 'least_visited', n_step: config.nStep ?? 4,
  }, input, key);
  const campaign = result.campaign;
  if (!campaign || campaign.project_id !== project.project_id || typeof campaign.campaign_id !== 'string' || !Number.isSafeInteger(campaign.version) || campaign.version < 1 || !Number.isSafeInteger(campaign.cursor) || !Number.isSafeInteger(campaign.round_limit) || campaign.cursor < 0 || campaign.round_limit < 1 || campaign.round_limit > 100000 || campaign.cursor > campaign.round_limit || !['ready', 'running', 'paused', 'cancelled', 'completed', 'interrupted'].includes(campaign.status) || !result.source?.source_id) invalid('The compiled campaign differs from its project.');
  playback(result.playback, project.project_id, artifact); return result;
}
