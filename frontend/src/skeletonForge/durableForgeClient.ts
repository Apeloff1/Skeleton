/** Saved source builds reuse the existing authenticated project/job/artifact owners. */
import api, { type ApiResult } from '../utils/apiClient';
import { getAuthEpoch } from '../auth/gameforgeAuth';
import { downloadConsoleArtifact, learningRequestKey, type ConsoleBuildArtifact } from '../product/gameLearningClient';
import type { RunPayload, RunRequest } from './types';

export type SavedForgeRequest = Omit<RunRequest, 'playtest'> & { playtest: 'off' };
export type ForgeProject = {
  project_id: string; name: string; console_id: 'forge:godot'; version: number;
  state?: string; tree_digest?: string; created_at?: string; updated_at?: string;
};
export type SavedForgeJob = {
  job_id: string; project_id: string; kind: 'forge_source'; status: string;
  request_id: string; request_digest: string; brief: SavedForgeRequest;
  project_version: number; resume_available?: boolean; recovery?: string;
  progress?: { completed: number; total: number; unit?: string } | null;
  result?: { state: string; build?: RunPayload; artifacts?: ConsoleBuildArtifact[]; source_manifest?: unknown } | null;
  error?: string | { code?: string; message?: string } | null;
  created_at?: string; updated_at?: string;
};
export type ForgeBuildPage = { builds: SavedForgeJob[]; next_cursor: string | null };
export type ForgeProjectDetail = { project: ForgeProject; builds: SavedForgeJob[]; next_cursor?: string | null };

const ROOT = '/api/skeleton/projects';
const ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const SHA = /^[a-f0-9]{64}$/;
const STATUSES = new Set(['queued', 'running', 'completed', 'interrupted', 'cancelled', 'failed']);
export class ForgeClientError extends Error {
  constructor(message: string, readonly status: number) { super(message); this.name = 'ForgeClientError'; }
}
export const forgeJobTerminal = (job: SavedForgeJob): boolean =>
  ['completed', 'interrupted', 'cancelled', 'failed'].includes(job.status);
function reject(message: string): never { throw new Error(message); }
function validId(value: unknown): value is string { return typeof value === 'string' && ID.test(value); }
function object(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function finiteJson(value: unknown, depth = 0): boolean {
  if (depth > 16) return false;
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (Array.isArray(value)) return value.length <= 4096 && value.every(item => finiteJson(item, depth + 1));
  return object(value) && Object.keys(value).length <= 4096
    && Object.entries(value).every(([key, item]) => !['__proto__', 'constructor', 'prototype'].includes(key) && finiteJson(item, depth + 1));
}

/** Explicitly source-only; a native-tested request must never be silently weakened. */
export function sourceOnlyForgeRequest(request: RunRequest | SavedForgeRequest, acknowledged: boolean): SavedForgeRequest {
  if (!acknowledged) reject('Review and accept the saved source-build scope first.');
  if (!object(request) || request.target !== 'godot' || typeof request.vision !== 'string'
      || !request.vision.trim() || request.vision.length > 4000) reject('Choose Godot and describe your game before saving a build.');
  const allowed = new Set(['vision', 'era', 'archetype', 'target', 'answers', 'operator_axes', 'generation',
    'include_files', 'playable_content', 'playable_archetype', 'playable_main_scene', 'galaxy_profile',
    'playtest', 'quest_content', 'quest_length', 'project_root', 'overwrite', 'blend', 't']);
  if (Object.keys(request).some(key => !allowed.has(key)) || !finiteJson(request)
      || JSON.stringify(request).length > 262144) reject('The saved build request exceeds its supported source contract.');
  if (('project_root' in request && request.project_root != null) || ('overwrite' in request && request.overwrite === true)) {
    reject('A source build cannot choose server paths or overwrite files.');
  }
  return JSON.parse(JSON.stringify({ ...request, include_files: true, playtest: 'off' })) as SavedForgeRequest;
}

export function checkedForgeProject(value: unknown): ForgeProject {
  if (!object(value) || !validId(value.project_id) || value.console_id !== 'forge:godot'
      || typeof value.name !== 'string' || !value.name.trim() || value.name.length > 200
      || !Number.isSafeInteger(value.version) || Number(value.version) < 1
      || value.tree_digest !== undefined && (typeof value.tree_digest !== 'string' || !SHA.test(value.tree_digest))) {
    reject('The saved source-project identity is invalid.');
  }
  return value as ForgeProject;
}

export function checkedForgeJob(value: unknown, projectId: string): SavedForgeJob {
  if (!object(value) || !validId(value.job_id) || value.project_id !== projectId || value.kind !== 'forge_source'
      || typeof value.status !== 'string' || !STATUSES.has(value.status)
      || typeof value.request_id !== 'string' || !value.request_id || value.request_id.length > 512
      || typeof value.request_digest !== 'string' || !SHA.test(value.request_digest)
      || !Number.isSafeInteger(value.project_version) || Number(value.project_version) < 1
      || !object(value.brief) || value.brief.target !== 'godot' || value.brief.playtest !== 'off'
      || value.brief.include_files !== true || !finiteJson(value.brief)
      || JSON.stringify(value).length > 2 * 1024 * 1024) reject('The saved build receipt does not belong to this source project.');
  if (value.result != null && (!object(value.result) || typeof value.result.state !== 'string')) reject('The saved build result is invalid.');
  const result = value.result as SavedForgeJob['result'];
  if (value.status === 'completed') {
    if (result?.state !== 'source_ready' || !object(result.build) || result.build.succeeded !== true
        || !Array.isArray(result.artifacts) || result.artifacts.length !== 1) reject('This saved build has no complete source result.');
    const artifact = result.artifacts[0];
    if (!validId(artifact?.artifact_id) || !SHA.test(artifact.digest) || !Number.isSafeInteger(artifact.bytes)
        || artifact.bytes < 1 || artifact.bytes > 16 * 1024 * 1024 || artifact.format !== 'zip'
        || artifact.download_path !== '/game-learning/projects/' + encodeURIComponent(projectId)
          + '/build-artifacts/' + encodeURIComponent(artifact.artifact_id)) reject('The saved source archive has an invalid identity.');
  }
  return value as SavedForgeJob;
}

async function data<T>(promise: Promise<ApiResult<T>>, epoch: number): Promise<T> {
  const response = await promise;
  if (epoch !== getAuthEpoch()) reject('The account changed; saved build observation was stopped.');
  if (!response.ok || !response.data) {
    const detail = (response.data as { detail?: unknown } | undefined)?.detail;
    const message = typeof detail === 'string' ? detail : object(detail) && typeof detail.message === 'string' ? detail.message : null;
    throw new ForgeClientError(message?.slice(0, 400) || (response.status === 401 ? 'Sign in to open your saved source projects.'
      : response.status === 409 ? 'The saved project changed. Refresh it before another action.' : 'The saved build service is unavailable. Your current questionnaire is unchanged.'), response.status);
  }
  return response.data;
}
function options(signal?: AbortSignal) { return { signal, timeoutMs: 20000, retries: 0 }; }
function projectPath(id: string): string { if (!validId(id)) reject('Invalid saved project.'); return ROOT + '/' + encodeURIComponent(id); }
function jobPath(projectId: string, jobId: string): string {
  if (!validId(jobId)) reject('Invalid saved build.'); return projectPath(projectId) + '/builds/' + encodeURIComponent(jobId);
}
export const savedForgeRequestKey = () => learningRequestKey('forge-source');
export async function listForgeProjects(signal?: AbortSignal): Promise<ForgeProject[]> {
  const result = await data(api.get<{ projects: unknown[] }>(ROOT, options(signal)), getAuthEpoch());
  if (!Array.isArray(result.projects) || result.projects.length > 128) reject('The source-project list is invalid.');
  return result.projects.map(checkedForgeProject);
}
export async function createForgeProject(name: string, key: string, signal?: AbortSignal): Promise<ForgeProject> {
  if (!name.trim() || name.trim().length > 120) reject('Name the source project using 1–120 characters.');
  const result = await data(api.post<{ project: unknown }>(ROOT, { name: name.trim(), idempotency_key: key }, options(signal)), getAuthEpoch());
  return checkedForgeProject(result.project);
}
export async function getForgeProject(id: string, signal?: AbortSignal): Promise<ForgeProjectDetail> {
  const result = await data(api.get<{ project: unknown; builds: unknown[]; next_cursor?: unknown }>(projectPath(id), options(signal)), getAuthEpoch());
  const project = checkedForgeProject(result.project);
  if (project.project_id !== id || !Array.isArray(result.builds) || result.builds.length > 24) reject('The source-project history is invalid.');
  if (result.next_cursor != null && !validId(result.next_cursor)) reject('The source-build history cursor is invalid.');
  return { project, builds: result.builds.map(value => checkedForgeJob(value, id)), next_cursor: result.next_cursor as string | null | undefined };
}
export async function listForgeBuilds(projectId: string, before: string, signal?: AbortSignal): Promise<ForgeBuildPage> {
  if (!validId(before)) reject('The older-build cursor is invalid.');
  const result = await data(api.get<{ builds: unknown[]; next_cursor: unknown }>(projectPath(projectId)
    + '/builds?before=' + encodeURIComponent(before) + '&limit=24', options(signal)), getAuthEpoch());
  if (!Array.isArray(result.builds) || result.builds.length > 24
      || result.next_cursor !== null && !validId(result.next_cursor)) reject('The older source-build history page is invalid.');
  const builds = result.builds.map(value => checkedForgeJob(value, projectId));
  if (new Set(builds.map(item => item.job_id)).size !== builds.length || result.next_cursor === before) reject('The source-build history cursor did not advance.');
  return { builds, next_cursor: result.next_cursor as string | null };
}
export async function submitForgeBuild(project: ForgeProject, run: SavedForgeRequest, key: string, signal?: AbortSignal): Promise<SavedForgeJob> {
  const result = await data(api.post<{ job: unknown }>(projectPath(project.project_id) + '/builds', {
    expected_version: project.version, idempotency_key: key, run, timeout_seconds: 60,
  }, options(signal)), getAuthEpoch());
  const job = checkedForgeJob(result.job, project.project_id);
  if (job.request_id !== key) reject('The saved build returned a different request identity.');
  return job;
}
export async function getForgeBuild(projectId: string, jobId: string, signal?: AbortSignal): Promise<SavedForgeJob> {
  const result = await data(api.get<{ job: unknown }>(jobPath(projectId, jobId), options(signal)), getAuthEpoch());
  const job = checkedForgeJob(result.job, projectId);
  if (job.job_id !== jobId) reject('The saved build identity changed.');
  return job;
}
export async function controlForgeBuild(projectId: string, jobId: string, action: 'cancel' | 'resume', signal?: AbortSignal): Promise<SavedForgeJob> {
  const result = await data(api.post<{ job: unknown }>(jobPath(projectId, jobId) + '/' + action, {}, options(signal)), getAuthEpoch());
  const job = checkedForgeJob(result.job, projectId);
  if (job.job_id !== jobId) reject('The saved build identity changed.');
  return job;
}
export async function downloadForgeBuild(job: SavedForgeJob, signal?: AbortSignal): Promise<Uint8Array> {
  const checked = checkedForgeJob(job, job.project_id);
  if (checked.status !== 'completed' || !checked.result?.artifacts?.[0]) reject('Wait for a complete saved source build.');
  return downloadConsoleArtifact(checked.project_id, checked.result.artifacts[0], { signal });
}
