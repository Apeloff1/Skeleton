import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { API_BASE } from '../../utils/apiBase';
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders } from '../auth/gameforgeAuth';
import { chatApiError, ChatClientError } from './chatErrors';

export type LearningRequest = { signal?: AbortSignal };
export type LearningSourceKind = 'text' | 'rom' | 'dragon' | 'project';
export type LearningReadiness = { message: string; code?: string; action?: string | null };
export type LearningConsole = {
  console_id: string; label: string; family?: string; engine_kind: string;
  available: boolean; readiness?: LearningReadiness | null; description?: string;
  supported_source_kinds: LearningSourceKind[]; editor_language?: string;
  default_program?: string; actions: string[];
  supported_formats?: string[]; limits?: Record<string, number>;
};
export type LearningAlgorithm = { id: string; label: string; available: boolean; readiness?: LearningReadiness | null };
export type LearningCatalogue = {
  schema_version?: string | number; consoles: LearningConsole[]; algorithms: LearningAlgorithm[];
  limits?: Record<string, number>; readiness?: LearningReadiness | null;
  generation_genres?: { id: string; label: string }[];
};
export type LearningFile = { path: string; content: string; language?: string; revision?: number };
export type LearningSource = {
  source_id: string; kind: LearningSourceKind; filename?: string; console_id?: string;
  source_digest?: string; rights_refs: string[]; created_at?: string;
  summary?: string; status?: string; size_bytes?: number; lineage_refs?: string[];
  metadata?: Record<string, unknown>;
  bundle?: { warnings?: string[]; metadata?: Record<string, unknown> }; state?: string;
};
export type LearningObservation = {
  frame_base64?: string; frame_media_type?: string; frame_digest?: string;
  state?: Record<string, unknown>; [key: string]: unknown;
};
export type LearningSession = {
  session_id: string; version?: number; source_id?: string; console_id?: string; steps?: number;
  total_reward?: number; terminal?: boolean; observation?: LearningObservation;
  metrics?: Record<string, unknown>; lineage_refs?: string[]; snapshot_digest?: string;
  created_at?: string; [key: string]: unknown;
  terminated?: boolean; truncated?: boolean; last_observation?: LearningObservation; last_frame?: Record<string, unknown>;
  actions?: string[]; environment?: Record<string, unknown>;
};
export type LearningCheckpoint = {
  checkpoint_id?: string; digest?: string; step?: number; episode?: number;
  created_at?: string; metrics?: Record<string, unknown>; [key: string]: unknown;
  policy_digest?: string; committed_episodes?: number; committed_updates?: number;
};
export type LearningJob = {
  job_id: string; project_id: string; kind: string; status: string;
  progress?: { completed: number; total: number; unit?: string } | null;
  metrics?: Record<string, unknown>; checkpoints?: LearningCheckpoint[];
  result?: Record<string, unknown> | null; error?: string | { message?: string; code?: string } | null;
  lineage_refs?: string[]; created_at?: string; updated_at?: string;
  resume_available?: boolean;
};
export type LearningGeneratedProject = {
  generated_id?: string; name?: string; target?: string; files?: LearningFile[];
  lineage_refs?: string[]; [key: string]: unknown;
};
export type LearningProject = {
  project_id: string; name: string; console_id: string; version: number;
  program_text: string; files?: LearningFile[]; sources: LearningSource[];
  sessions: LearningSession[]; jobs: LearningJob[]; generated_projects?: LearningGeneratedProject[];
  metrics?: Record<string, unknown>; lineage_refs?: string[]; created_at?: string; updated_at?: string; entrypoint?: string; policy_id?: string | null; environment_actions?: string[];
};
export type ReviewedDragonSource = { source_ref: string; source_id: string; source_revision: string; title: string; url?: string; current_review: boolean };
export type LearningProjectSummary = Pick<LearningProject, 'project_id' | 'name' | 'console_id' | 'version' | 'created_at' | 'updated_at'>;
export type LearningExport = { filename: string; mimeType: string; content: string; contentDigest: string; version: number };

const ROOT = '/api/game-learning';
const TERMINAL = new Set(['completed', 'complete', 'succeeded', 'failed', 'cancelled', 'interrupted']);
export function learningJobTerminal(job: LearningJob): boolean { return TERMINAL.has(job.status); }
export function learningRequestKey(action: string): string {
  const random = globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
  return 'game-learning:' + action + ':' + random;
}
function options(input: LearningRequest = {}, key?: string) {
  return { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 30000, idempotencyKey: key };
}
async function data<T>(promise: Promise<ApiResult<T>>, message: string): Promise<T> {
  const result = await promise;
  if (!result.ok || result.data === null) throw chatApiError(result, message);
  return result.data;
}
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function project(value: LearningProject): LearningProject {
  if (!value || typeof value.project_id !== 'string' || !value.project_id || typeof value.name !== 'string'
    || typeof value.console_id !== 'string' || !Number.isSafeInteger(value.version) || value.version < 1
    || typeof value.program_text !== 'string' || value.program_text.length > 128000
    || !Array.isArray(value.sources) || value.sources.length > 64 || !Array.isArray(value.sessions) || value.sessions.length > 512
    || !Array.isArray(value.jobs) || value.jobs.length > 512 || (value.files?.length ?? 0) > 96) invalid('The server returned an invalid game project.');
  for (const file of value.files || []) if (typeof file.path !== 'string' || typeof file.content !== 'string' || file.content.length > 128000) invalid('A project file exceeds the editor bounds.');
  for (const source of value.sources) if (!source || typeof source.source_id !== 'string' || typeof source.kind !== 'string' || !Array.isArray(source.rights_refs) || source.rights_refs.length > 64) invalid('The server returned an invalid source identity.');
  for (const session of value.sessions) if (!session || typeof session.session_id !== 'string' || !session.session_id) invalid('The server returned an invalid session identity.');
  value.sessions = [...value.sessions].sort((a, b) => String(a.created_at || a.updated_at || '').localeCompare(String(b.created_at || b.updated_at || '')));
  for (const current of value.jobs) job(current, value.project_id);
  return value;
}
function job(value: LearningJob, projectId?: string): LearningJob {
  if (!value || typeof value.job_id !== 'string' || !value.job_id || typeof value.project_id !== 'string'
    || projectId && value.project_id !== projectId || typeof value.kind !== 'string' || typeof value.status !== 'string'
    || (value.checkpoints?.length ?? 0) > 512) invalid('The server returned an invalid learning job.');
  if (value.progress && (!Number.isFinite(value.progress.completed) || !Number.isFinite(value.progress.total)
    || value.progress.completed < 0 || value.progress.total <= 0 || value.progress.completed > value.progress.total)) invalid('Learning progress is invalid.');
  return value;
}
function path(projectId: string): string {
  if (!projectId || projectId.length > 128) invalid('Project identity is invalid.');
  return ROOT + '/projects/' + encodeURIComponent(projectId);
}
export async function getLearningCatalogue(input: LearningRequest = {}): Promise<LearningCatalogue> {
  const result = await data(api.get<LearningCatalogue>(ROOT + '/catalog', options(input)), 'Game learning is unavailable.');
  if (!Array.isArray(result?.consoles) || result.consoles.length > 512 || !Array.isArray(result.algorithms) || result.algorithms.length > 32) invalid('The engine catalogue is invalid.');
  const ids = new Set<string>();
  for (const console of result.consoles) {
    if (!console || typeof console.console_id !== 'string' || !console.console_id || ids.has(console.console_id)
      || typeof console.label !== 'string' || typeof console.available !== 'boolean' || typeof console.engine_kind !== 'string'
      || !Array.isArray(console.actions) || console.actions.length > 128 || console.actions.some(value => typeof value !== 'string')
      || !Array.isArray(console.supported_source_kinds)) invalid('The catalogue contains an invalid console.');
    ids.add(console.console_id);
  }
  for (const algorithm of result.algorithms) if (!algorithm || typeof algorithm.id !== 'string' || typeof algorithm.label !== 'string' || typeof algorithm.available !== 'boolean') invalid('The catalogue contains an invalid learner.');
  return result;
}
export async function getReviewedDragonSources(input: LearningRequest = {}): Promise<ReviewedDragonSource[]> {
  const result = await data(api.get<{ sources: ReviewedDragonSource[] }>(ROOT + '/dragon-sources?limit=32', options(input)), 'Reviewed Dragon sources could not be loaded.');
  if (!Array.isArray(result.sources) || result.sources.length > 32 || result.sources.some(source => !source || typeof source.source_ref !== 'string'
    || !source.source_ref.startsWith('dragon:') || source.source_ref.length > 512 || typeof source.title !== 'string' || source.current_review !== true)) invalid('The reviewed Dragon inventory is invalid.');
  return result.sources;
}
export async function listLearningProjects(input: LearningRequest = {}): Promise<LearningProjectSummary[]> {
  const result = await data(api.get<{ projects: LearningProjectSummary[] }>(ROOT + '/projects', options(input)), 'Projects could not be loaded.');
  if (!Array.isArray(result.projects) || result.projects.length > 256) invalid('The project list exceeds its bounds.');
  for (const value of result.projects) if (!value || typeof value.project_id !== 'string' || !value.project_id || typeof value.name !== 'string' || typeof value.console_id !== 'string' || !Number.isSafeInteger(value.version) || value.version < 1) invalid('The project list contains an invalid identity.');
  return result.projects;
}
export async function getLearningProject(projectId: string, input: LearningRequest = {}): Promise<LearningProject> {
  const result = await data(api.get<{ project: LearningProject }>(path(projectId), options(input)), 'This project could not be opened.');
  const current = project(result.project);
  if (current.project_id !== projectId) invalid('The server returned a different project.');
  return current;
}
export async function createLearningProject(name: string, consoleId: string, input: LearningRequest = {}, key = learningRequestKey('create')): Promise<LearningProject> {
  const result = await data(api.post<{ project: LearningProject }>(ROOT + '/projects', {
    name: name.trim(), console_id: consoleId, idempotency_key: key,
  }, options(input, key)), 'The project could not be created.');
  return project(result.project);
}
export async function saveLearningEditor(current: LearningProject, programText: string, files?: LearningFile[], input: LearningRequest = {}, key = learningRequestKey('editor')): Promise<LearningProject> {
  const payload = files ? { files: files.map(file => ({ path: file.path, content: file.content, language: file.language, revision: file.revision })), path: current.entrypoint || undefined }
    : { program_text: programText };
  const result = await data(api.patch<{ project: LearningProject }>(path(current.project_id) + '/editor', {
    expected_version: current.version, idempotency_key: key, ...payload,
  }, options(input, key)), 'Source changes could not be saved. Refresh before retrying a revision conflict.');
  return project(result.project);
}
export type LearningIngestInput = {
  kind: LearningSourceKind; filename?: string; contentBase64?: string; text?: string; dragonRef?: string; rightsRefs: string[];
};
export async function ingestLearningSource(current: LearningProject, source: LearningIngestInput, input: LearningRequest = {}, key = learningRequestKey('ingest')): Promise<LearningProject> {
  const result = await data(api.post<{ project: LearningProject }>(path(current.project_id) + '/sources', {
    expected_version: current.version, idempotency_key: key, kind: source.kind,
    filename: source.filename, content_base64: source.contentBase64, text: source.text, dragon_ref: source.dragonRef,
    rights_refs: source.rightsRefs, rights_acknowledged: true,
  }, options(input, key)), 'The source could not be ingested.');
  return project(result.project);
}
export type LearningSimulationInput = { sourceId?: string; sessionId?: string; sessionVersion?: number; reset?: boolean; action?: string; steps: number; seed: number };
export async function simulateLearningProject(current: LearningProject, simulation: LearningSimulationInput, input: LearningRequest = {}, key = learningRequestKey('simulate')): Promise<LearningProject> {
  const result = await data(api.post<{ project: LearningProject }>(path(current.project_id) + '/simulate', {
    expected_version: current.version, idempotency_key: key, source_id: simulation.sourceId,
    session_id: simulation.sessionId, expected_session_version: simulation.sessionVersion, reset: simulation.reset, seed: simulation.seed,
    ...(simulation.reset ? {} : simulation.action ? simulation.steps === 1 ? { action: simulation.action } : { actions: Array(simulation.steps).fill(simulation.action) } : { steps: simulation.steps }),
  }, options(input, key)), 'The engine action could not be executed.');
  return project(result.project);
}
export async function startLearningTraining(current: LearningProject, config: {
  sessionIds: string[]; algorithm: string; epochs: number; seed: number; episodeSteps?: number; sourceId?: string;
  freshPolicy?: boolean;
}, input: LearningRequest = {}, key = learningRequestKey('train')): Promise<LearningJob> {
  const result = await data(api.post<{ job: LearningJob }>(path(current.project_id) + '/train', {
    expected_version: current.version, idempotency_key: key, session_ids: config.sessionIds,
    algorithm: config.algorithm, epochs: config.epochs, seed: config.seed, episode_steps: config.episodeSteps, source_id: config.sourceId, fresh_policy: config.freshPolicy,
  }, options(input, key)), 'Local training could not be started.');
  return job(result.job, current.project_id);
}
export async function generateLearningProject(current: LearningProject, config: { title: string; genre: string; seed: number; complexity: number; sourceId?: string; policyId?: string }, input: LearningRequest = {}, key = learningRequestKey('generate')): Promise<LearningJob> {
  const result = await data(api.post<{ job: LearningJob }>(path(current.project_id) + '/generate', {
    expected_version: current.version, idempotency_key: key, title: config.title, genre: config.genre, seed: config.seed,
    complexity: config.complexity, source_id: config.sourceId, policy_id: config.policyId,
  }, options(input, key)), 'The game project could not be generated.');
  return job(result.job, current.project_id);
}
export async function getLearningJob(jobId: string, input: LearningRequest = {}): Promise<LearningJob> {
  const result = await data(api.get<{ job: LearningJob }>(ROOT + '/jobs/' + encodeURIComponent(jobId), options(input)), 'Learning progress could not be loaded.');
  const current = job(result.job);
  if (current.job_id !== jobId) invalid('The server returned a different learning job.');
  return current;
}
export async function cancelLearningJob(jobId: string, input: LearningRequest = {}, key = learningRequestKey('cancel')): Promise<LearningJob> {
  const result = await data(api.post<{ job: LearningJob }>(ROOT + '/jobs/' + encodeURIComponent(jobId) + '/cancel', {}, options(input, key)), 'The learning job could not be stopped.');
  return job(result.job);
}
export async function resumeLearningJob(jobId: string, input: LearningRequest = {}): Promise<LearningJob> {
  const result = await data(api.post<{ job: LearningJob }>(ROOT + '/jobs/' + encodeURIComponent(jobId) + '/resume', {}, options(input)), 'The learning job could not be resumed.');
  return job(result.job);
}
export async function revokeLearningSource(current: LearningProject, sourceId: string, input: LearningRequest = {}): Promise<LearningProject> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  input.signal?.addEventListener('abort', abort, { once: true });
  if (input.signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 30000);
  try {
    const response = await fetch(API_BASE + path(current.project_id) + '/sources/' + encodeURIComponent(sourceId), {
      method: 'DELETE', headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ expected_version: current.version }), signal: controller.signal,
    });
    const raw = await response.text();
    if (raw.length > 8 * 1024 * 1024) invalid('The source withdrawal response exceeded its bound.');
    let value;
    try { value = JSON.parse(raw); } catch { invalid('The source withdrawal response is invalid.'); }
    if (!response.ok) throw new ChatClientError(typeof value.detail?.message === 'string' ? value.detail.message : 'The source could not be withdrawn.', {
      kind: response.status === 409 ? 'conflict' : response.status === 403 ? 'authorization' : 'execution', status: response.status,
    });
    return project(value.project);
  } finally { clearTimeout(timer); input.signal?.removeEventListener('abort', abort); }
}
export async function exportLearningProject(current: LearningProject, input: LearningRequest = {}, generatedJobId?: string): Promise<LearningExport> {
  const result = await data(api.get<{
    project_id: string; snapshot_version: number; filename: string; media_type: string; content: string; content_digest: string;
  }>(path(current.project_id) + '/export?expected_version=' + current.version + (generatedJobId ? '&generated_job_id=' + encodeURIComponent(generatedJobId) : ''), options(input)), 'The project could not be exported.');
  if (result.project_id !== current.project_id || result.snapshot_version !== current.version || typeof result.content !== 'string'
    || new TextEncoder().encode(result.content).byteLength > 8 * 1024 * 1024 || !/^[0-9a-f]{64}$/.test(result.content_digest)
    || typeof result.filename !== 'string' || result.filename.includes('/') || result.filename.includes('\\')
    || result.media_type.split(';', 1)[0] !== 'application/json') invalid('The project export is invalid.');
  const digest = await digestStringAsync(CryptoDigestAlgorithm.SHA256, result.content);
  if (digest !== result.content_digest) invalid('The exported project content changed.');
  return { filename: result.filename, mimeType: result.media_type, content: result.content, contentDigest: digest, version: result.snapshot_version };
}
