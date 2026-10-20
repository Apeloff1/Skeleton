import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';
import { learningRequestKey, type LearningProject, type LearningRequest } from './gameLearningClient';

export type StudioCompletionMode = 'native' | 'original';
export type StudioCompletionRequirement = 'edit' | 'build' | 'preview' | 'simulate' | 'review' | 'package' | 'export';
export type StudioNumericMemoryPolicy = 'goal_only' | 'reuse_compatible' | 'reset';
export type StudioQualityPolicy = {
  schema_version: 'skeleton.game.studio_quality_policy.v1';
  baseline_review_job_id?: string | null;
  max_refinement_rounds: number;
  min_available_frames: number;
  min_executed_steps: number;
  max_error_findings: number;
  max_warning_findings: number;
  require_no_regression: boolean;
  restore_on_regression: boolean;
  adaptive_ranking?: boolean;
  numeric_memory_policy?: StudioNumericMemoryPolicy;
};
export type StudioQualityMeasuredProgress = {
  schema_version: 'skeleton.game.studio_quality_progress.v1';
  policy_digest: string; project_id: string; project_version: number; head_digest: string;
  baseline: null | { job_id: string; review_digest: string; input_digest: string; head_digest: string; project_version: number; protocol_digest: string };
  candidate: null | { job_id: string; review_digest: string; input_digest: string; head_digest: string;
    executed_steps: number | null; available_frames: number | null; finding_counts: { error: number; warning: number; info: number };
    priority_findings: { finding_id: string; code: string; severity: string; message: string; evidence_refs: string[] }[];
    comparison_digest: string | null; comparison_status: string | null };
  status: 'baseline_required' | 'candidate_required' | 'accepted' | 'rejected';
  refinement_rounds: number; remaining_refinement_rounds: number; restorations: number;
  incumbent_source_restored: boolean; failures: { code: string; [key: string]: unknown }[];
  regressions: string[]; verified: boolean; quality_certified: false; scope: string; receipt_digest: string;
};
export type StudioQualityProgress = StudioQualityMeasuredProgress | {
  schema_version: 'skeleton.game.studio_quality_progress.v1'; status: 'unavailable'; verified: false;
  quality_certified: false; error: { code: string; message: string };
};
export type StudioGoal = {
  goal_id: string; project_id: string; version: number; status: string; goal: string;
  execution_mode: 'plan' | 'run'; allow_edits: boolean; cursor: number; max_steps: number;
  model_calls: number; max_model_calls: number; jobs_started: number; max_jobs: number; max_output_tokens?: number;
  expires_at?: string; last_step?: Record<string, unknown> | null; steps: Record<string, unknown>[];
  error?: string | Record<string, unknown> | null; pending_job_id?: string | null;
  recovery?: { can_retry: boolean; can_resume: boolean; can_renew: boolean; target: StudioGoalRetryTarget | null; reason?: string | null; pending_kind?: string | null; pending_id?: string | null; legacy_read_only?: boolean; can_new_planner_attempt?: boolean; pending_status?: string | null; child_resume_available?: boolean; child_terminal?: boolean; automatic_continuation_available?: boolean; next_action?: 'wait' | 'retry' | 'advance' | 'inspect_dependency' | 'resume' | 'authorize' | 'inspect' };
  integrity?: { status: string; history_digest?: string | null; state_digest?: string | null }; outcome?: { completion_reason?: string | null; goal_satisfaction_verified: false };
  completion_mode?: StudioCompletionMode; completion_requirements?: string[]; completion?: { verified: boolean; missing?: string[]; checks?: Record<string, { verified: boolean; [key: string]: unknown }>; scope?: string; receipt_digest?: string };
  workflow?: { remaining_actions: number; active: boolean };
  quality_gate?: StudioQualityPolicy; quality?: StudioQualityProgress;
  adaptive_learning?: StudioNumericAdaptation;
  [key: string]: unknown;
};
export type StudioNumericAdaptation = {
  schema_version: 'skeleton.game.studio_numeric_adaptation.v1'; status: string;
  context_digest?: string | null; checkpoint_digest?: string | null;
  observations_seen?: number; training_steps?: number; rejected_updates?: number;
  replay_size?: number; advice: { expected_spec_digest: string; edits: { op: 'set_field'; path: string[]; value: number }[] }[];
  production_authority: false; scope: string;
  numeric_memory?: {
    policy: StudioNumericMemoryPolicy; status: string; reused_goals: number; reused_observations: number;
    provenance_goals: number; epoch: string | null; reset_barrier: boolean; exclusion_counts: Record<string, number>;
  };
};
export type StudioGoalRetryTarget = 'planner' | 'action' | 'job' | 'play' | 'reconcile';
export type StudioGoalConfig = { goal: string; maxSteps: number; executionMode: 'plan' | 'run'; allowEdits: boolean; authorizationSeconds: number; maxModelCalls: number; maxJobs: number; max_output_tokens?: number; completionMode?: StudioCompletionMode; completionRequirements?: StudioCompletionRequirement[]; qualityGate?: StudioQualityPolicy };
const ROOT = '/api/game-studio-agent';
function invalid(message: string): never { throw new ChatClientError(message, { kind: 'protocol', retryable: false }); }
function id(value: string) { if (!value || value.length > 128) invalid('The studio goal identity is invalid.'); return encodeURIComponent(value); }
async function request<T>(method: 'get' | 'post', route: string, body: unknown, input: LearningRequest = {}, key?: string): Promise<T> { const token = getAuthToken(); const options = { signal: input.signal, headers: authHeaders(), retries: 0, timeoutMs: 180000, idempotencyKey: key }; const result: ApiResult<T> = await (method === 'get' ? api.get<T>(ROOT + route, options) : api.post<T>(ROOT + route, body, options)); if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Reopen the studio assistant.', { kind: 'authorization', retryable: false }); if (!result.ok || result.data === null) throw chatApiError(result, 'The studio goal could not be updated.'); return result.data; }
function boundedInteger(value: unknown, minimum: number, maximum: number): value is number {
  return Number.isSafeInteger(value) && (value as number) >= minimum && (value as number) <= maximum;
}
function digest(value: unknown): value is string { return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value); }
function qualityPolicy(value: StudioQualityPolicy): StudioQualityPolicy {
  if (!value || value.schema_version !== 'skeleton.game.studio_quality_policy.v1'
    || !boundedInteger(value.max_refinement_rounds, 1, 4) || !boundedInteger(value.min_available_frames, 1, 25)
    || !boundedInteger(value.min_executed_steps, 1, 512) || !boundedInteger(value.max_error_findings, 0, 128)
    || !boundedInteger(value.max_warning_findings, 0, 128) || typeof value.require_no_regression !== 'boolean'
    || typeof value.restore_on_regression !== 'boolean'
    || value.adaptive_ranking !== undefined && typeof value.adaptive_ranking !== 'boolean'
    || value.numeric_memory_policy !== undefined && !['goal_only', 'reuse_compatible', 'reset'].includes(value.numeric_memory_policy)
    || value.numeric_memory_policy !== undefined && value.numeric_memory_policy !== 'goal_only' && value.adaptive_ranking !== true
    || value.baseline_review_job_id != null && (typeof value.baseline_review_job_id !== 'string' || !value.baseline_review_job_id || value.baseline_review_job_id.length > 128)) invalid('The measured quality policy is invalid.');
  return { schema_version: value.schema_version, ...(value.baseline_review_job_id ? { baseline_review_job_id: value.baseline_review_job_id } : {}),
    max_refinement_rounds: value.max_refinement_rounds, min_available_frames: value.min_available_frames,
    min_executed_steps: value.min_executed_steps, max_error_findings: value.max_error_findings,
    max_warning_findings: value.max_warning_findings, require_no_regression: value.require_no_regression, restore_on_regression: value.restore_on_regression,
    adaptive_ranking: value.adaptive_ranking ?? false, numeric_memory_policy: value.numeric_memory_policy ?? 'goal_only' };
}
function qualityProgress(value: StudioQualityProgress, projectId: string): void {
  if (value?.status === 'unavailable') {
    if (value.schema_version !== 'skeleton.game.studio_quality_progress.v1' || value.verified !== false || value.quality_certified !== false
      || !value.error || typeof value.error.code !== 'string' || !value.error.code || value.error.code.length > 160
      || typeof value.error.message !== 'string' || value.error.message.length > 4000) invalid('The quality dependency status is invalid.');
    return;
  }
  if (!value || value.schema_version !== 'skeleton.game.studio_quality_progress.v1' || value.project_id !== projectId
    || !boundedInteger(value.project_version, 1, Number.MAX_SAFE_INTEGER) || !digest(value.policy_digest) || !digest(value.head_digest) || !digest(value.receipt_digest)
    || !['baseline_required', 'candidate_required', 'accepted', 'rejected'].includes(value.status)
    || !boundedInteger(value.refinement_rounds, 0, 16) || !boundedInteger(value.remaining_refinement_rounds, 0, 4)
    || !boundedInteger(value.restorations, 0, 16) || typeof value.incumbent_source_restored !== 'boolean'
    || typeof value.verified !== 'boolean' || value.verified !== (value.status === 'accepted') || value.quality_certified !== false
    || !Array.isArray(value.failures) || value.failures.length > 128 || value.failures.some(row => !row || typeof row.code !== 'string' || row.code.length > 160)
    || !Array.isArray(value.regressions) || value.regressions.length > 128 || value.regressions.some(row => typeof row !== 'string' || row.length > 160)
    || typeof value.scope !== 'string' || value.scope.length > 2000) invalid('The measured quality observation is invalid.');
  if (value.baseline && (typeof value.baseline.job_id !== 'string' || !digest(value.baseline.review_digest)
    || !digest(value.baseline.input_digest) || !digest(value.baseline.head_digest) || !digest(value.baseline.protocol_digest)
    || !boundedInteger(value.baseline.project_version, 1, Number.MAX_SAFE_INTEGER))) invalid('The pinned quality baseline is invalid.');
  const candidate = value.candidate;
  if (candidate && (typeof candidate.job_id !== 'string' || !digest(candidate.review_digest) || !digest(candidate.input_digest) || !digest(candidate.head_digest)
    || candidate.head_digest !== value.head_digest || candidate.executed_steps !== null && !boundedInteger(candidate.executed_steps, 0, 1000000)
    || candidate.available_frames !== null && !boundedInteger(candidate.available_frames, 0, 1000000)
    || !candidate.finding_counts || !['error', 'warning', 'info'].every(key => boundedInteger(candidate.finding_counts[key as keyof typeof candidate.finding_counts], 0, 128))
    || !Array.isArray(candidate.priority_findings) || candidate.priority_findings.length > 128
    || candidate.priority_findings.some(row => !row || typeof row.message !== 'string' || row.message.length > 4000)
    || candidate.comparison_digest !== null && !digest(candidate.comparison_digest)
    || candidate.comparison_status !== null && typeof candidate.comparison_status !== 'string')) invalid('The current quality candidate is invalid.');
  if (value.verified && (!value.baseline || !candidate || value.failures.length)) invalid('The accepted quality receipt is incomplete.');
}
function goal(value: StudioGoal, projectId?: string) {
  if (value?.max_output_tokens !== undefined && (!Number.isSafeInteger(value.max_output_tokens) || value.max_output_tokens < 256 || value.max_output_tokens > 4096)) invalid('The persisted AI decision-token budget is invalid.');
  if (value?.completion_mode !== undefined && !['native', 'original'].includes(value.completion_mode)) invalid('The saved goal workflow mode is invalid.');
  if (value?.quality_gate) qualityPolicy(value.quality_gate);
  if (value?.quality) qualityProgress(value.quality, value.project_id);
  const adaptation = value?.adaptive_learning;
  if (adaptation && (adaptation.schema_version !== 'skeleton.game.studio_numeric_adaptation.v1'
    || adaptation.production_authority !== false || typeof adaptation.status !== 'string' || adaptation.status.length > 128
    || !Array.isArray(adaptation.advice) || adaptation.advice.length > 3
    || ['observations_seen', 'training_steps', 'rejected_updates', 'replay_size'].some(key => adaptation[key as keyof StudioNumericAdaptation] !== undefined && !boundedInteger(adaptation[key as keyof StudioNumericAdaptation], 0, 1000000))
    || adaptation.advice.some(proposal => !digest(proposal.expected_spec_digest) || !Array.isArray(proposal.edits) || proposal.edits.length > 64
      || proposal.edits.some(edit => edit.op !== 'set_field' || !Array.isArray(edit.path) || edit.path.length !== 3 || edit.path.some(part => typeof part !== 'string' || part.length > 128) || !Number.isFinite(edit.value))))) invalid('The numeric learning projection is invalid.');
  const numericMemory = adaptation?.numeric_memory;
  if (numericMemory && (!['goal_only', 'reuse_compatible', 'reset'].includes(numericMemory.policy)
    || typeof numericMemory.status !== 'string' || numericMemory.status.length > 128
    || !boundedInteger(numericMemory.reused_goals, 0, 8) || !boundedInteger(numericMemory.provenance_goals, 0, 8)
    || !boundedInteger(numericMemory.reused_observations, 0, 32) || typeof numericMemory.reset_barrier !== 'boolean'
    || numericMemory.epoch !== null && (typeof numericMemory.epoch !== 'string' || !numericMemory.epoch || numericMemory.epoch.length > 128)
    || !numericMemory.exclusion_counts || Array.isArray(numericMemory.exclusion_counts) || typeof numericMemory.exclusion_counts !== 'object'
    || Object.entries(numericMemory.exclusion_counts).length > 10
    || Object.entries(numericMemory.exclusion_counts).some(([key, count]) => !key || key.length > 128 || !boundedInteger(count, 0, 32)))) invalid('The numeric memory provenance is invalid.');
  const recovery = value?.recovery;
  if (recovery && ([recovery.can_retry, recovery.can_resume, recovery.can_renew].some(flag => typeof flag !== 'boolean') || recovery.target !== null && !['planner', 'action', 'job', 'play', 'reconcile'].includes(recovery.target) || recovery.can_new_planner_attempt !== undefined && typeof recovery.can_new_planner_attempt !== 'boolean')) invalid('The goal recovery capabilities are invalid.');
  if (recovery && (recovery.automatic_continuation_available !== undefined && typeof recovery.automatic_continuation_available !== 'boolean' || recovery.next_action !== undefined && !['wait', 'retry', 'advance', 'inspect_dependency', 'resume', 'authorize', 'inspect'].includes(recovery.next_action))) invalid('The saved continuation hint is invalid.');
  if (value?.integrity && (!['verified', 'legacy_unverified'].includes(value.integrity.status) || value.integrity.status === 'verified' && (!/^[a-f0-9]{64}$/.test(value.integrity.history_digest || '') || !/^[a-f0-9]{64}$/.test(value.integrity.state_digest || '')))) invalid('The goal operation journal is invalid.');
  if (value?.workflow && (typeof value.workflow.active !== 'boolean' || !Number.isSafeInteger(value.workflow.remaining_actions) || value.workflow.remaining_actions < 0 || value.workflow.remaining_actions > 4)) invalid('The saved goal workflow exceeds its action bounds.');
  if (!value || typeof value.goal_id !== 'string' || typeof value.project_id !== 'string' || projectId && value.project_id !== projectId || !Number.isSafeInteger(value.version) || value.version < 1 || !Number.isSafeInteger(value.cursor) || !Number.isSafeInteger(value.max_steps) || value.cursor < 0 || value.max_steps < 1 || value.max_steps > 16 || value.cursor > value.max_steps || !boundedInteger(value.model_calls, 0, 16) || !boundedInteger(value.max_model_calls, 1, 16) || value.model_calls > value.max_model_calls || !boundedInteger(value.jobs_started, 0, 8) || !boundedInteger(value.max_jobs, 0, 8) || value.jobs_started > value.max_jobs || !['plan', 'run'].includes(value.execution_mode) || typeof value.allow_edits !== 'boolean' || !Array.isArray(value.steps) || value.steps.length > 16 || JSON.stringify(value).length > 4 * 1024 * 1024) invalid('The persisted studio goal is invalid.'); return value; }
export async function listStudioGoals(projectId: string, input: LearningRequest = {}) { const result = await request<{ goals: StudioGoal[] }>('get', '/projects/' + id(projectId) + '/goals', null, input); if (!Array.isArray(result.goals) || result.goals.length > 128) invalid('The goal history exceeds its bounds.'); return result.goals.map(value => goal(value, projectId)); }
export async function getStudioGoal(goalId: string, input: LearningRequest = {}) { const result = await request<{ goal: StudioGoal }>('get', '/goals/' + id(goalId), null, input); const value = goal(result.goal); if (value.goal_id !== goalId) invalid('A different studio goal was returned.'); return value; }
export async function createStudioGoal(project: LearningProject, config: StudioGoalConfig, input: LearningRequest = {}, key = learningRequestKey('studio-goal')) { if (config.completionMode === 'original' && config.completionRequirements?.length && project.files?.some(file => ['game/editor/console.json', 'game/studio/session.json'].includes(file.path))) throw new Error('Use a separate original-game project for the desktop workflow.'); const supported = config.completionMode === 'original' ? ['edit', 'simulate', 'review', 'package', 'export'] : ['edit', 'build', 'preview', 'export']; if (config.completionRequirements && (config.completionRequirements.length > supported.length || new Set(config.completionRequirements).size !== config.completionRequirements.length || config.completionRequirements.some(requirement => !supported.includes(requirement)))) throw new Error('Choose completion requirements supported by this workflow.'); const quality = config.qualityGate ? qualityPolicy(config.qualityGate) : undefined; if (quality && (config.executionMode !== 'run' || config.completionMode !== 'original' || !config.completionRequirements?.includes('simulate') || !config.completionRequirements?.includes('review') || quality.restore_on_regression && !config.allowEdits)) throw new Error('Measured acceptance requires an original-game run with simulation and review; restoration also requires the explicit edit grant.'); if (!boundedInteger(config.maxJobs, 0, 8)) throw new Error('Choose a background-job budget between 0 and 8.'); const outputTokens = config.max_output_tokens ?? 1024; if (!Number.isSafeInteger(outputTokens) || outputTokens < 256 || outputTokens > 4096) throw new Error('Choose an AI decision-token budget between 256 and 4096.'); const result = await request<{ goal: StudioGoal }>('post', '/projects/' + id(project.project_id) + '/goals', { expected_version: project.version, idempotency_key: key, goal: config.goal, max_steps: config.maxSteps, execution_mode: config.executionMode, allow_edits: config.allowEdits, authorization_seconds: config.authorizationSeconds, max_model_calls: config.maxModelCalls, max_jobs: config.maxJobs, max_output_tokens: outputTokens, completion_requirements: config.completionRequirements, ...(quality ? { quality_gate: quality } : {}), ...(config.completionMode ? { completion_mode: config.completionMode } : {}) }, input, key); const value = goal(result.goal, project.project_id); if (value.max_output_tokens !== outputTokens) invalid('The issued goal differs from the requested decision-token budget.'); if (config.completionMode && value.completion_mode !== config.completionMode) invalid('The issued goal differs from the requested workflow mode.'); if (quality && JSON.stringify(qualityPolicy(value.quality_gate!)) !== JSON.stringify(quality)) invalid('The issued quality policy differs from the requested acceptance bounds.'); return value; }
export async function advanceStudioGoal(current: StudioGoal, steps: number, input: LearningRequest = {}, key = learningRequestKey('studio-advance')) { const result = await request<{ goal: StudioGoal }>('post', '/goals/' + id(current.goal_id) + '/advance', { expected_goal_version: current.version, idempotency_key: key, steps }, input, key); const value = goal(result.goal, current.project_id); if (value.goal_id !== current.goal_id) invalid('A different studio goal was advanced.'); return value; }
export async function controlStudioGoal(current: StudioGoal, action: 'pause' | 'resume' | 'cancel', input: LearningRequest = {}, key = learningRequestKey('studio-' + action)) { const result = await request<{ goal: StudioGoal }>('post', '/goals/' + id(current.goal_id) + '/control', { expected_goal_version: current.version, idempotency_key: key, action }, input, key); const value = goal(result.goal, current.project_id); if (value.goal_id !== current.goal_id) invalid('A different studio goal was controlled.'); return value; }
export async function retryStudioGoal(current: StudioGoal, target: StudioGoalRetryTarget, input: LearningRequest = {}, key = learningRequestKey('studio-retry'), newPlannerAttempt = false) { if (!['planner', 'action', 'job', 'play', 'reconcile'].includes(target) || newPlannerAttempt && target !== 'planner') invalid('This operation cannot be recovered through the studio assistant.'); const result = await request<{ goal: StudioGoal }>('post', '/goals/' + id(current.goal_id) + '/retry', { expected_goal_version: current.version, idempotency_key: key, target, new_planner_attempt: newPlannerAttempt }, input, key); const value = goal(result.goal, current.project_id); if (value.goal_id !== current.goal_id) invalid('A different studio goal was recovered.'); return value; }
export async function authorizeStudioGoal(current: StudioGoal, authorizationSeconds: number, input: LearningRequest = {}, key = learningRequestKey('studio-authorization')) { if (!Number.isSafeInteger(authorizationSeconds) || authorizationSeconds < 60 || authorizationSeconds > 3600) throw new Error('Renew this goal for between 1 and 60 minutes.'); const result = await request<{ goal: StudioGoal }>('post', '/goals/' + id(current.goal_id) + '/authorization', { expected_goal_version: current.version, idempotency_key: key, authorization_seconds: authorizationSeconds }, input, key); const value = goal(result.goal, current.project_id); if (value.goal_id !== current.goal_id) invalid('A different studio goal was authorized.'); return value; }
