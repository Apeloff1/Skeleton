import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { learningRequestKey, type LearningJob, type LearningProject, type LearningRequest } from './gameLearningClient';
import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';

export type StudioCampaign = {
  campaign_id: string; project_id: string; version: number;
  status: 'ready' | 'running' | 'paused' | 'cancelled' | 'completed' | 'interrupted';
  cursor: number; round_limit: number; slice_rounds: number; active_job_id?: string | null;
  champion?: Record<string, unknown> | null; metrics?: Record<string, unknown>;
  updated_at?: string; [key: string]: unknown;
};
export type StudioRound = Record<string, unknown>;
export type StudioLesson = Record<string, unknown>;
export type CampaignConfig = { roundLimit: number; sliceRounds: number; episodes: number; maxSteps: number; seed: number; sourceId?: string; policyId?: string; autoContinue?: boolean; authorizationSeconds?: number; evaluationSeeds?: number; curriculum?: string; objectiveWeights?: Record<string, number>; maxMeanStepMs?: number | null; maxDeathRegression?: number; maxWorstSeedRegression?: number };
export type StudioLearningCatalogue = { objectives: Record<string, { unit: string; default_weight: number }>; curricula: string[]; proposal_families: string[]; evaluation_seeds: { minimum: number; maximum: number; default: number }; objective_weight_bounds: [number, number]; [key: string]: unknown };
export type StudioChampion = { campaign_id: string; campaign_version: number; cursor: number; scope: string; champion: { round_index: number | null; round_digest: string | null; request_digest: string; policy_digest: string | null; tree_digest: string | null; files: { path: string; content: string }[]; eligible_for_adoption: boolean; reason?: string; target_id: string; kind: string }; production_promotion_authorized: false };
const ROOT = '/api/game-studio-learning';
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function id(value: string) { if (!value || value.length > 128) invalid('The learning record identity is invalid.'); return encodeURIComponent(value); }
async function request<T>(method: 'get' | 'post', path: string, body: unknown, input: LearningRequest = {}, key?: string): Promise<T> {
  const token = getAuthToken(); const options = { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 30000, idempotencyKey: key };
  const result: ApiResult<T> = await (method === 'get' ? api.get<T>(ROOT + path, options) : api.post<T>(ROOT + path, body, options));
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen the learning campaign.', { kind: 'authorization', retryable: false });
  if (!result.ok || result.data === null) throw chatApiError(result, 'The learning campaign could not be updated.'); return result.data;
}
function campaign(value: StudioCampaign, projectId?: string) {
  if (!value || typeof value.campaign_id !== 'string' || typeof value.project_id !== 'string' || projectId && value.project_id !== projectId || !Number.isSafeInteger(value.version) || value.version < 1 || !Number.isSafeInteger(value.cursor) || !Number.isSafeInteger(value.round_limit) || value.cursor < 0 || value.round_limit < 1 || value.round_limit > 100000 || value.cursor > value.round_limit || !Number.isSafeInteger(value.slice_rounds) || value.slice_rounds < 1 || value.slice_rounds > 8 || !['ready', 'running', 'paused', 'cancelled', 'completed', 'interrupted'].includes(value.status) || JSON.stringify(value).length > 262144) invalid('The persisted learning campaign is invalid.'); return value;
}
export async function listStudioCampaigns(projectId: string, input: LearningRequest = {}) { const result = await request<{ campaigns: StudioCampaign[] }>('get', '/projects/' + id(projectId) + '/campaigns', null, input); if (!Array.isArray(result.campaigns) || result.campaigns.length > 64) invalid('The learning campaign catalogue exceeds its bounds.'); return result.campaigns.map(value => campaign(value, projectId)); }
export async function getStudioCampaign(campaignId: string, input: LearningRequest = {}) { const result = await request<{ campaign: StudioCampaign }>('get', '/campaigns/' + id(campaignId), null, input); const value = campaign(result.campaign); if (value.campaign_id !== campaignId) invalid('A different learning campaign was returned.'); return value; }
export async function createStudioCampaign(project: LearningProject, config: CampaignConfig, input: LearningRequest = {}, key = learningRequestKey('campaign-create')) { const result = await request<{ campaign: StudioCampaign }>('post', '/projects/' + id(project.project_id) + '/campaigns', { expected_version: project.version, idempotency_key: key, round_limit: config.roundLimit, slice_rounds: config.sliceRounds, episodes: config.episodes, max_steps: config.maxSteps, seed: config.seed, source_id: config.sourceId, policy_id: config.policyId, auto_continue: config.autoContinue ?? false, authorization_seconds: config.authorizationSeconds ?? 21600, evaluation_seeds: config.evaluationSeeds ?? 3, curriculum: config.curriculum ?? 'mixed', objective_weights: config.objectiveWeights, max_mean_step_ms: config.maxMeanStepMs ?? null, max_death_regression: config.maxDeathRegression ?? 0, max_worst_seed_regression: config.maxWorstSeedRegression ?? 0 }, input, key); return campaign(result.campaign, project.project_id); }
export async function pulseStudioCampaign(current: StudioCampaign, input: LearningRequest = {}, key = learningRequestKey('campaign-pulse')) { const result = await request<{ campaign: StudioCampaign; job: LearningJob }>('post', '/campaigns/' + id(current.campaign_id) + '/pulse', { expected_campaign_version: current.version, idempotency_key: key }, input, key); campaign(result.campaign, current.project_id); if (result.campaign.campaign_id !== current.campaign_id || !result.job || result.job.project_id !== current.project_id || typeof result.job.job_id !== 'string') invalid('The learning slice belongs to a different campaign.'); return result; }
export async function controlStudioCampaign(current: StudioCampaign, action: 'pause' | 'resume' | 'cancel', input: LearningRequest = {}, key = learningRequestKey('campaign-' + action)) { const result = await request<{ campaign: StudioCampaign }>('post', '/campaigns/' + id(current.campaign_id) + '/' + action, { expected_campaign_version: current.version, idempotency_key: key }, input, key); const value = campaign(result.campaign, current.project_id); if (value.campaign_id !== current.campaign_id) invalid('A different learning campaign was updated.'); return value; }
export async function getStudioRounds(campaignId: string, after = 0, input: LearningRequest = {}) { const result = await request<{ campaign_id: string; rounds: StudioRound[]; next_cursor: number | null }>('get', '/campaigns/' + id(campaignId) + '/rounds?after=' + after + '&limit=16', null, input); if (result.campaign_id !== campaignId || !Array.isArray(result.rounds) || result.rounds.length > 16 || result.next_cursor !== null && (!Number.isSafeInteger(result.next_cursor) || result.next_cursor < after || result.next_cursor > 100000) || JSON.stringify(result).length > 4 * 1024 * 1024) invalid('The measured learning round page is invalid.'); return result; }
export async function getStudioLessons(projectId: string, query = '', input: LearningRequest = {}) { const result = await request<{ lessons: StudioLesson[] }>('get', '/projects/' + id(projectId) + '/lessons?q=' + encodeURIComponent(query.slice(0, 256)) + '&limit=32', null, input); if (!Array.isArray(result.lessons) || result.lessons.length > 32 || JSON.stringify(result).length > 1024 * 1024) invalid('The remembered lesson page is invalid.'); return result.lessons; }

export async function getStudioLearningCatalogue(input: LearningRequest = {}): Promise<StudioLearningCatalogue> { const value = await request<StudioLearningCatalogue>('get', '/catalog', null, input); if (!value || !value.objectives || Object.keys(value.objectives).length > 16 || !Array.isArray(value.curricula) || value.curricula.length > 16 || !Array.isArray(value.objective_weight_bounds) || value.objective_weight_bounds.length !== 2 || JSON.stringify(value).length > 131072) invalid('The measured learning catalogue is invalid.'); return value; }
export async function getStudioChampion(campaignId: string, input: LearningRequest = {}): Promise<StudioChampion> { const value = await request<StudioChampion>('get', '/campaigns/' + id(campaignId) + '/champion', null, input); if (value.campaign_id !== campaignId || !Number.isSafeInteger(value.campaign_version) || !value.champion || typeof value.champion.eligible_for_adoption !== 'boolean' || !Array.isArray(value.champion.files) || value.champion.files.length > 128 || value.champion.files.some(file => typeof file.path !== 'string' || typeof file.content !== 'string') || value.scope !== 'measured_champion_source_only' || value.champion.eligible_for_adoption && !/^[a-f0-9]{64}$/.test(value.champion.round_digest || '') || JSON.stringify(value).length > 8 * 1024 * 1024) invalid('The measured champion handoff is invalid.'); return value; }
export async function adoptStudioChampion(current: StudioCampaign, project: LearningProject, champion: StudioChampion, input: LearningRequest = {}, key = learningRequestKey('champion-adopt')) { if (champion.campaign_id !== current.campaign_id || current.project_id !== project.project_id || !champion.champion.eligible_for_adoption) throw new Error('This champion does not have a current source-adoption handoff.'); const value = await request<{ campaign: StudioCampaign; project: LearningProject; handoff: unknown; source_only: boolean; policy_promoted: boolean }>('post', '/campaigns/' + id(current.campaign_id) + '/champion/adopt', { expected_campaign_version: current.version, expected_version: project.version, idempotency_key: key, champion_round_digest: champion.champion.round_digest }, input, key); if (value.project?.project_id !== project.project_id || value.campaign?.campaign_id !== current.campaign_id || value.source_only !== true || value.policy_promoted !== false) invalid('The champion adoption changed its declared scope.'); campaign(value.campaign, project.project_id); return value; }
export async function authorizeStudioCampaign(current: StudioCampaign, autoContinue: boolean, authorizationSeconds: number, input: LearningRequest = {}, key = learningRequestKey('campaign-authorize')) { const value = await request<{ campaign: StudioCampaign }>('post', '/campaigns/' + id(current.campaign_id) + '/authorization', { expected_campaign_version: current.version, idempotency_key: key, auto_continue: autoContinue, authorization_seconds: authorizationSeconds }, input, key); const result = campaign(value.campaign, current.project_id); if (result.campaign_id !== current.campaign_id) invalid('Authorization belongs to a different campaign.'); return result; }
export async function exportStudioChampion(campaignId: string, input: LearningRequest = {}) { const token = getAuthToken(); const value = await request<{ filename: string; media_type: string; content: string; content_digest: string; scope: string; attachments_embedded: boolean }>('get', '/campaigns/' + id(campaignId) + '/champion/export', null, input); if (typeof value.filename !== 'string' || value.filename.includes('/') || value.filename.includes('\\') || value.media_type !== 'application/json' || typeof value.content !== 'string' || new TextEncoder().encode(value.content).byteLength > 8 * 1024 * 1024 || !/^[a-f0-9]{64}$/.test(value.content_digest) || value.attachments_embedded !== false || value.scope !== 'measured_champion_source_only') invalid('The champion source export is invalid.'); if (await digestStringAsync(CryptoDigestAlgorithm.SHA256, value.content) !== value.content_digest || token !== getAuthToken() || input.signal?.aborted) invalid('The champion export content or account changed.'); return { filename: value.filename, mimeType: value.media_type, content: value.content, contentDigest: value.content_digest }; }

export async function getStudioLessonPage(projectId: string, query = '', cursor?: string | null, input: LearningRequest = {}) {
  if (cursor && cursor.length > 256) invalid('The lesson cursor exceeds its bound.');
  const value = await request<{ lessons: StudioLesson[]; next_cursor: string | null; search_mode?: string; legacy_indexing_pending?: boolean }>('get', '/projects/' + id(projectId) + '/lessons?q=' + encodeURIComponent(query.slice(0, 256)) + '&limit=32' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), null, input);
  if (!Array.isArray(value.lessons) || value.lessons.length > 32 || value.next_cursor !== null && (typeof value.next_cursor !== 'string' || value.next_cursor.length > 256) || JSON.stringify(value).length > 4 * 1024 * 1024) invalid('The remembered lesson page is invalid.'); return value;
}


export type StudioMirrorFrame = {
  schema_version?: string; data_uri?: string; frame_digest?: string; step?: number;
  state?: Record<string, unknown>; telemetry_raster_available?: boolean;
  pixel_frame_available?: boolean; runtime_kind?: string;
};
export type StudioMirrorLane = {
  angle: string; seed: number; steps: number; actions: string[];
  rejected_actions: number; total_reward: number;
  source_digest: string; environment_digest: string;
  snapshot_digest: string; last_observation: Record<string, number>;
  frames: StudioMirrorFrame[]; digest: string; native_frames: false;
};
export type StudioMirrorViews = {
  schema_version: string; campaign_id: string; campaign_cursor: number;
  campaign_status: string; sample: number; angles: string[];
  lanes: StudioMirrorLane[]; workers_used: number;
  spectator_only: true; frames_show_training_episodes: false;
  view_kind: string; digest: string;
};
export type StudioScenarioDraft = {
  proposal: {
    schema_version: string; proposal_id: string; base_digest: string;
    reason: string; scene_seed: number | null;
    operations: { scope: string; path: string; op: string; value: unknown }[];
  };
  variant_source_digest: string; support: string;
  mechanics_inspiration: string[]; sales_rank_is_quality_evidence: false;
};
export type StudioScenarioDiscovery = {
  schema_version: string; campaign_id: string; engine: string;
  scenarios: StudioScenarioDraft[]; measured_committed_rounds: number;
  requires_rights_and_operator_training_admission: true;
  automatic_training_performed: false; scenarios_verified_as_successful: false;
};
export type StudioEngineTestManifest = {
  schema_version: string; engine: string; registered_action_count: number;
  registered_actions: string[]; field_axes: {
    name: string; type: string; cases: unknown[]; checks: string[];
  }[]; mandatory_checks: { id: string; required: boolean; count?: number }[];
  angles: string[]; verified_passes: number; execution_status: 'not_run';
  combinatorial_state_exhaustiveness_claimed: false; digest: string;
};
export type StudioSalesReference = {
  reference: string; chart: string; rank: number; units_millions: number | null;
  editor: string; motif: string;
};
export type StudioSalesCatalog = {
  schema_version: string; entries: StudioSalesReference[];
  sources: Record<string, { source_url: string; as_of: string;
    type: string; region: string; limitations: string }>;
  evidence_use: string; digest: string;
};

export async function getStudioMirrorViews(
  campaignId: string, sample: number, lanes = 4, steps = 12,
  input: LearningRequest = {},
): Promise<StudioMirrorViews> {
  if (!Number.isSafeInteger(sample) || sample < 0 || sample > 255
      || !Number.isSafeInteger(lanes) || lanes < 1 || lanes > 6
      || !Number.isSafeInteger(steps) || steps < 1 || steps > 24) invalid('Spectator limits differ.');
  const result = await request<StudioMirrorViews>(
    'get', '/campaigns/' + id(campaignId) + '/mirror-views?sample=' + sample +
    '&lanes=' + lanes + '&steps=' + steps, null, input,
  );
  if (result.campaign_id !== campaignId || !result.spectator_only
      || result.frames_show_training_episodes !== false
      || !Array.isArray(result.lanes) || result.lanes.length > lanes
      || result.lanes.some(lane => !Array.isArray(lane.frames)
          || lane.frames.length > 5 || lane.native_frames !== false
          || !Number.isSafeInteger(lane.steps) || lane.steps > steps
          || !/^[a-f0-9]{64}$/.test(lane.digest))
      || JSON.stringify(result).length > 3 * 1024 * 1024) invalid('Mirrored simulation source or limits differ.');
  return result;
}
export async function getStudioScenarioDrafts(campaignId: string, input: LearningRequest = {}) {
  const result = await request<StudioScenarioDiscovery>(
    'get', '/campaigns/' + id(campaignId) + '/scenario-drafts?limit=4', null, input,
  );
  if (result.campaign_id !== campaignId || !Array.isArray(result.scenarios)
      || result.scenarios.length > 4 || result.automatic_training_performed !== false
      || result.scenarios_verified_as_successful !== false
      || JSON.stringify(result).length > 65536) invalid('Scenario drafts have unapproved source or authority.');
  return result;
}
export async function getStudioEngineTestManifest(editor: string, input: LearningRequest = {}) {
  const result = await request<StudioEngineTestManifest>(
    'get', '/engines/' + id(editor) + '/test-manifest', null, input,
  );
  if (result.engine !== editor || result.execution_status !== 'not_run'
      || result.verified_passes !== 0 || result.combinatorial_state_exhaustiveness_claimed !== false
      || !Array.isArray(result.registered_actions) || !Array.isArray(result.field_axes)
      || !Array.isArray(result.mandatory_checks)
      || JSON.stringify(result).length > 262144) invalid('Engine test manifest is not an unverified bounded plan.');
  return result;
}
export async function getStudioSalesReferences(input: LearningRequest = {}) {
  const result = await request<StudioSalesCatalog>(
    'get', '/research/sales-informed-scenarios', null, input,
  );
  if (!Array.isArray(result.entries) || result.entries.length > 100
      || typeof result.sources !== 'object' || JSON.stringify(result).length > 65536
  ) invalid('Original game design references contain invalid ranking evidence.');
  return result;
}

export type StudioEngineProbePage = {
  engine: string; release_certified: false; full_engine_state_exhausted: false;
  contract: { engine: string; source_validation: true; same_seed_replay: true;
    snapshot_reexecution: true; foreign_game_control_rejected: true; digest: string };
  actions: {
    engine: string; start: number; count: number; registered_action_count: number;
    next_offset: number | null; action_protocol_passes: number;
    accepted_initial_actions: number; rejected_initial_actions: number;
    action_probes: {
      action: string; accepted_in_initial_state: boolean;
      rejected_in_initial_state: boolean; replay_verified: true; end_state_digest: string;
    }[];
    digest: string;
  };
};
export async function runStudioEngineProbePage(
  editor: string, offset = 0, input: LearningRequest = {},
): Promise<StudioEngineProbePage> {
  if (!Number.isSafeInteger(offset) || offset < 0 || offset > 100000) invalid('Engine test offset outside bounds.');
  const value = await request<StudioEngineProbePage>(
    'get', '/engines/' + id(editor) + '/probes?offset=' + offset + '&limit=8',
    null, input,
  );
  if (value.engine !== editor || value.release_certified !== false
      || value.full_engine_state_exhausted !== false
      || value.actions.start !== offset || value.actions.count > 8
      || !Array.isArray(value.actions.action_probes)
      || value.actions.action_probes.length !== value.actions.count
      || value.actions.action_probes.some(entry => entry.replay_verified !== true)
      || JSON.stringify(value).length > 65536) invalid('Executable engine probe evidence differs.');
  return value;
}
