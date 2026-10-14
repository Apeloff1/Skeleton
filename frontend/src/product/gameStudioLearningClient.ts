import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { learningRequestKey, type LearningJob, type LearningProject, type LearningRequest } from './gameLearningClient';

export type StudioCampaign = {
  campaign_id: string; project_id: string; version: number;
  status: 'ready' | 'running' | 'paused' | 'cancelled' | 'completed' | 'interrupted';
  cursor: number; round_limit: number; slice_rounds: number; active_job_id?: string | null;
  champion?: Record<string, unknown> | null; metrics?: Record<string, unknown>;
  updated_at?: string; [key: string]: unknown;
};
export type StudioRound = Record<string, unknown>;
export type StudioLesson = Record<string, unknown>;
export type CampaignConfig = { roundLimit: number; sliceRounds: number; episodes: number; maxSteps: number; seed: number; policyId?: string; autoContinue?: boolean; authorizationSeconds?: number };
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
export async function createStudioCampaign(project: LearningProject, config: CampaignConfig, input: LearningRequest = {}, key = learningRequestKey('campaign-create')) { const result = await request<{ campaign: StudioCampaign }>('post', '/projects/' + id(project.project_id) + '/campaigns', { expected_version: project.version, idempotency_key: key, round_limit: config.roundLimit, slice_rounds: config.sliceRounds, episodes: config.episodes, max_steps: config.maxSteps, seed: config.seed, policy_id: config.policyId, auto_continue: config.autoContinue ?? false, authorization_seconds: config.authorizationSeconds ?? 21600 }, input, key); return campaign(result.campaign, project.project_id); }
export async function pulseStudioCampaign(current: StudioCampaign, input: LearningRequest = {}, key = learningRequestKey('campaign-pulse')) { const result = await request<{ campaign: StudioCampaign; job: LearningJob }>('post', '/campaigns/' + id(current.campaign_id) + '/pulse', { expected_campaign_version: current.version, idempotency_key: key }, input, key); campaign(result.campaign, current.project_id); if (result.campaign.campaign_id !== current.campaign_id || !result.job || result.job.project_id !== current.project_id || typeof result.job.job_id !== 'string') invalid('The learning slice belongs to a different campaign.'); return result; }
export async function controlStudioCampaign(current: StudioCampaign, action: 'pause' | 'resume' | 'cancel', input: LearningRequest = {}, key = learningRequestKey('campaign-' + action)) { const result = await request<{ campaign: StudioCampaign }>('post', '/campaigns/' + id(current.campaign_id) + '/' + action, { expected_campaign_version: current.version, idempotency_key: key }, input, key); const value = campaign(result.campaign, current.project_id); if (value.campaign_id !== current.campaign_id) invalid('A different learning campaign was updated.'); return value; }
export async function getStudioRounds(campaignId: string, after = 0, input: LearningRequest = {}) { const result = await request<{ campaign_id: string; rounds: StudioRound[]; next_cursor: number | null }>('get', '/campaigns/' + id(campaignId) + '/rounds?after=' + after + '&limit=16', null, input); if (result.campaign_id !== campaignId || !Array.isArray(result.rounds) || result.rounds.length > 16 || result.next_cursor !== null && (!Number.isSafeInteger(result.next_cursor) || result.next_cursor < after || result.next_cursor > 100000) || JSON.stringify(result).length > 4 * 1024 * 1024) invalid('The measured learning round page is invalid.'); return result; }
export async function getStudioLessons(projectId: string, query = '', input: LearningRequest = {}) { const result = await request<{ lessons: StudioLesson[] }>('get', '/projects/' + id(projectId) + '/lessons?q=' + encodeURIComponent(query.slice(0, 256)) + '&limit=32', null, input); if (!Array.isArray(result.lessons) || result.lessons.length > 32 || JSON.stringify(result).length > 1024 * 1024) invalid('The remembered lesson page is invalid.'); return result.lessons; }
