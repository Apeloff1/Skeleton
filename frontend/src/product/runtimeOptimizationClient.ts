import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import api, { type ApiResult } from '../utils/apiClient';
import { ChatClientError, chatApiError } from './chatErrors';

type Fields = Record<string, unknown>;
export type RuntimeLearningPartition = {
  partition_id?: string; task_class?: string; model_selection_digest?: string; state_version?: number;
  samples?: number; fresh_samples?: number; optimizer_steps?: number; readiness?: string;
  quarantined?: boolean; uncertainty?: number; prediction_error?: number; confidence_reasons?: string[];
  drift?: { active?: boolean; score?: number; events?: number; cooldown_remaining?: number; fast_loss?: number; slow_loss?: number; last_prequential_loss?: number; prequential_count?: number };
  last_healthy?: { available?: boolean; observations?: number; optimizer_step?: number; checkpoint_digest?: string };
  rollback_count?: number; generation?: number;
  source_provenance?: { latest_source_digest?: string; recent_source_count?: number; source_switches?: number; latest_source_samples?: number };
  optimizer_cost?: { terminal_updates?: number; replay_updates?: number; maintenance_updates?: number; total_updates?: number };
};
export type RuntimeServingState = {
  available?: boolean;
  provider_id?: string; model_id?: string; model_digest?: string; route_id?: string; active?: boolean;
  policy?: { enabled?: boolean; min_effective_concurrency?: number; max_effective_concurrency?: number };
  capacity?: { operator_max_concurrency?: number; effective_concurrency?: number; background_limit?: number; active_interactive?: number; active_background?: number; queued_interactive?: number; queued_background?: number; per_tenant_active_limit?: number; per_tenant_queue_limit?: number; effective_queue_limit?: number };
  pressure?: { level?: string; reason?: string; latency_ewma_ms?: number; queue_wait_ewma_ms?: number; failure_ewma?: number; resource?: Fields; samples?: number };
  cache?: { entries?: number; bytes?: number; max_bytes?: number; evictions?: number; expirations?: number; singleflight_active?: number; singleflight_hits?: number; singleflight_tenants?: number; largest_tenant_singleflight_waiters?: number };
  fairness?: { active_tenants?: number; queued_tenants?: number; largest_tenant_active?: number; largest_tenant_queued?: number; rotations?: number; aged_background_admissions?: number; tenant_limit_rejections?: number; memory_shed_rejections?: number; load_shed_rejections?: number; oldest_interactive_wait_ms?: number; oldest_background_wait_ms?: number; max_observed_queue_wait_ms?: number };
  draining?: boolean;
};
export type RuntimeMaintenanceTask = {
  task_id?: string; kind?: string; state?: string; attempts?: number; failures?: number; updated_at_ns?: number;
  source_digest?: string; retryable?: boolean; retry_reason?: string | null;
};
export type RuntimeControlState = {
  schema_version: 'skeleton.ai.runtime_control.v1';
  policy_version: number;
  reconciliation?: { state?: 'applied' | 'pending'; error_code?: string | null };
  actor_id: string;
  tenant_id: string;
  serving: RuntimeServingState & { models?: RuntimeServingState[] };
  learning: {
    available?: boolean;
    policy?: { enabled?: boolean; min_samples?: number };
    totals_health?: 'healthy' | 'quarantined';
    totals?: { outcomes?: number; completed?: number; degraded?: number; failed?: number; cancelled?: number; resource_failures?: number; telemetry_errors?: number; provider_attempts?: number } | null;
    scope_id?: string;
    partitions?: RuntimeLearningPartition[];
    limits?: { partition_offset?: number; total_partitions?: number; has_more_partitions?: boolean; returned_partitions?: number; returned_outcomes?: number };
  };
  maintenance: {
    available?: boolean;
    policy?: { enabled?: boolean; augmentation_enabled?: boolean };
    status?: { state?: string; active_tasks?: number; foreground_requests?: number; last_run_ns?: number | null; next_run_ns?: number | null; last_reason?: string; coordination_state?: 'synchronized' | 'unavailable'; coordination_error?: string | null };
    queued_tasks?: number;
    recent_tasks?: RuntimeMaintenanceTask[];
    ownership?: { owner_id?: string; host_id?: string; state?: string; heartbeat_ns?: number; foreground_requests?: number; physical_tasks?: number };
    leases?: { resource_id?: string; scope_id?: string; owner_id?: string; fencing_token?: number; state?: string; heartbeat_ns?: number; lease_until_ns?: number; drained_at_ns?: number | null }[];
    recovery?: { blocked_tasks?: number; clock_jump_count?: number; last_clock_jump_reason?: string | null };
    coordination?: { state?: 'observed' | 'degraded'; error_code?: string | null };
    quiescence?: { host_foreground_requests?: number; registered_host_owners?: number; observation?: string };
    chunk_results?: { retained?: number; reserved?: number; reusable_unverified?: number; shared_retained?: number; maximum?: number; backpressure?: boolean };
    acknowledgements?: { pending?: number; failed_attempts?: number; next_retry_ns?: number | null; last_error?: string | null; callback_available?: boolean };
  };
  execution?: {
    available?: boolean; active_executions?: number; active_lifecycle_leases?: number; faulted?: boolean;
    recovery?: { maximum_recovery_drivers?: number; page_limit?: number; scan_in_progress?: boolean; scanned?: number; started?: number; last_error?: string | null; driver_failures?: number; driver_finalization_failures?: number; last_driver_error?: string | null };
  };
  ratchet: { available: boolean; baseline?: Fields | null };
};

type AccountScope = { token: string; tenantId: string; principalId: string; role: string };
export type RuntimeControlObservation = { state: RuntimeControlState; scope: AccountScope; observedAt: number };
export type RuntimeControlAction = 'trim_cache' | 'clear_cache' | 'drain' | 'resume';
export type RuntimeControlChange = {
  serving_route_id?: string;
  serving?: { enabled?: boolean; max_effective_concurrency?: number };
  learning?: { enabled: boolean };
  maintenance?: { enabled?: boolean; augmentation_enabled?: boolean };
  action?: RuntimeControlAction;
};
export type RuntimeLearningCheckpoint = {
  schema_version: 'skeleton.runtime.learning.checkpoint.v1';
  tenant_id: string; scope_id: string; partition_id: string; task_class: string;
  model_selection_digest: string; feature_schema: 'skeleton.runtime.learning.features.v1';
  state_version: number; state_digest: string; source_snapshot_digest: string;
  checkpoint_digest: string; state: Fields;
};
/** Keep canonical text opaque across JSON transports; parsed data is a preview only. */
export type RuntimeLearningCheckpointFile = { checkpoint: RuntimeLearningCheckpoint; checkpointJson: string };
export type RuntimeLearningAction = 'import' | 'reset' | 'restore_last_healthy';
export const MAX_RUNTIME_CHECKPOINT_BYTES = 256 * 1024;
const ROOT = '/api/ai/runtime-control';
const OPTIONS = { timeoutMs: 15000, retries: 0, maxResponseChars: 256 * 1024 };
const HASH = /^[a-f0-9]{64}$/;

function invalid(message: string): never {
  throw new ChatClientError(message, { kind: 'protocol', code: 'runtime_control_invalid', retryable: false });
}
function object(value: unknown): value is Fields { return !!value && typeof value === 'object' && !Array.isArray(value); }
function identity(value: unknown): string {
  if (typeof value !== 'string' || !value.trim() || value.length > 512 || /[\u0000-\u001f]/.test(value)) invalid('The runtime account identity is incomplete. Verify your session again.');
  return value.trim();
}
function current(token: string, signal?: AbortSignal): void {
  if (signal?.aborted) throw new ChatClientError('Runtime observation detached.', { kind: 'cancelled', retryable: false });
  if (token !== getAuthToken()) throw new ChatClientError('Your account changed. Refresh the runtime panel for the current account.', { kind: 'authorization', code: 'runtime_account_changed', retryable: false });
}
async function read<T>(request: Promise<ApiResult<T>>, token: string, signal?: AbortSignal): Promise<T> {
  const result = await request;
  current(token, signal);
  if (!result.ok || result.data == null) throw chatApiError(result, 'Runtime optimization could not be observed. Check the AI engine connection and refresh.');
  return result.data;
}
function sameAccount(left: AccountScope, right: AccountScope): boolean {
  return left.token === right.token && left.tenantId === right.tenantId && left.principalId === right.principalId;
}
async function account(signal?: AbortSignal, expected?: AccountScope): Promise<AccountScope> {
  const token = getAuthToken();
  current(token, signal);
  const me = await read(api.get<unknown>('/api/auth/me', { ...OPTIONS, signal, headers: authHeaders() }), token, signal);
  if (!object(me) || me.authenticated !== true || !object(me.user)) throw new ChatClientError('Sign in to observe runtime optimization.', { kind: 'authorization', retryable: false });
  const scope = { token, tenantId: identity(me.user.tenant_id || 'default'), principalId: identity(me.user.email || me.user.user_id), role: typeof me.user.role === 'string' ? me.user.role : 'viewer' };
  if (expected && !sameAccount(scope, expected)) throw new ChatClientError('Your account changed. Refresh before changing runtime policy.', { kind: 'authorization', code: 'runtime_account_changed', retryable: false });
  return scope;
}

/** Bounded, numeric operational telemetry only. No result is a quality certificate. */
function state(value: unknown, scope: AccountScope): RuntimeControlState {
  if (!object(value) || value.schema_version !== 'skeleton.ai.runtime_control.v1' || !Number.isSafeInteger(value.policy_version) || Number(value.policy_version) < 1
    || !object(value.serving) || !object(value.learning) || !object(value.maintenance) || !object(value.ratchet) || typeof value.ratchet.available !== 'boolean') invalid('The runtime control response is incomplete or uses an unsupported version.');
  if (identity(value.actor_id) !== scope.principalId || identity(value.tenant_id) !== scope.tenantId) throw new ChatClientError('The runtime observation belongs to another account. Refresh the current session.', { kind: 'authorization', code: 'runtime_scope_mismatch', retryable: false });
  let nodes = 0;
  const bounded = (item: unknown, depth: number): void => {
    if (++nodes > 12000 || depth > 12) invalid('The runtime observation exceeds its supported bounds.');
    if (typeof item === 'number' && !Number.isFinite(item) || typeof item === 'string' && item.length > 4096) invalid('The runtime observation contains invalid telemetry.');
    if (Array.isArray(item)) { if (item.length > 256) invalid('The runtime observation contains too many records.'); item.forEach(child => bounded(child, depth + 1)); }
    else if (object(item)) Object.values(item).forEach(child => bounded(child, depth + 1));
  };
  bounded(value, 0);
  for (const section of [value.serving, value.learning, value.maintenance]) {
    if (section.available !== undefined && typeof section.available !== 'boolean') invalid('Runtime capability availability is invalid.');
    if (section.policy !== undefined && !object(section.policy)) invalid('The observed runtime policy is invalid.');
    if (object(section.policy) && section.policy.enabled !== undefined && typeof section.policy.enabled !== 'boolean') invalid('The observed runtime policy switch is invalid.');
  }
  if (object(value.maintenance.policy) && value.maintenance.policy.augmentation_enabled !== undefined && typeof value.maintenance.policy.augmentation_enabled !== 'boolean') invalid('The observed replay adaptation switch is invalid.');
  for (const key of ['capacity', 'pressure', 'cache']) if (value.serving[key] !== undefined && !object(value.serving[key])) invalid('The serving observation is invalid.');
  if (value.serving.draining !== undefined && typeof value.serving.draining !== 'boolean') invalid('The serving drain state is invalid.');
  if (value.learning.totals !== undefined && value.learning.totals !== null && !object(value.learning.totals) || value.learning.partitions !== undefined && !Array.isArray(value.learning.partitions)
    || value.maintenance.status !== undefined && !object(value.maintenance.status) || value.maintenance.recent_tasks !== undefined && !Array.isArray(value.maintenance.recent_tasks)) invalid('The learning or maintenance observation is invalid.');
  if (Array.isArray(value.learning.partitions) && value.learning.partitions.some(row => !object(row)) || Array.isArray(value.maintenance.recent_tasks) && value.maintenance.recent_tasks.some(row => !object(row))) invalid('The runtime observation contains an invalid record.');
  if (Array.isArray(value.maintenance.recent_tasks)) for (const row of value.maintenance.recent_tasks as Fields[]) {
    if (row.retryable !== undefined && typeof row.retryable !== 'boolean' || row.retry_reason != null && (typeof row.retry_reason !== 'string' || row.retry_reason.length > 512)) invalid('Maintenance retry eligibility is invalid.');
    if (row.retryable === true && (!HASH.test(String(row.task_id)) || !HASH.test(String(row.source_digest)) || !Number.isSafeInteger(row.attempts) || Number(row.attempts) < 0 || Number(row.attempts) > 1000000)) invalid('The eligible maintenance retry lacks an exact task, source or attempt binding.');
  }
  if (value.execution !== undefined) {
    if (!object(value.execution)) invalid('The execution recovery observation is invalid.');
    for (const key of ['available', 'faulted']) if (value.execution[key] !== undefined && typeof value.execution[key] !== 'boolean') invalid('The execution supervisor flags are invalid.');
    for (const key of ['active_executions', 'active_lifecycle_leases']) if (value.execution[key] !== undefined && (!Number.isSafeInteger(value.execution[key]) || Number(value.execution[key]) < 0)) invalid('The execution supervisor counters are invalid.');
    if (value.execution.recovery !== undefined && !object(value.execution.recovery)) invalid('The execution recovery counters are invalid.');
  }
  if (Array.isArray(value.learning.partitions)) for (const row of value.learning.partitions as Fields[]) {
    if (row.confidence_reasons !== undefined && (!Array.isArray(row.confidence_reasons) || row.confidence_reasons.length > 32 || row.confidence_reasons.some(reason => typeof reason !== 'string' || reason.length > 160))) invalid('Learner confidence constraints are invalid.');
    for (const key of ['drift', 'last_healthy', 'source_provenance', 'optimizer_cost']) if (row[key] !== undefined && !object(row[key])) invalid('A learner observation contains invalid diagnostic state.');
  }
  if (value.maintenance.leases !== undefined && (!Array.isArray(value.maintenance.leases) || value.maintenance.leases.some(row => !object(row)))) invalid('The maintenance lease observation is invalid.');
  for (const key of ['ownership', 'recovery', 'coordination', 'quiescence', 'chunk_results', 'acknowledgements']) if (value.maintenance[key] !== undefined && !object(value.maintenance[key])) invalid('The maintenance ownership observation is invalid.');
  if (value.serving.models !== undefined) {
    if (!Array.isArray(value.serving.models) || value.serving.models.length > 8) invalid('The local serving catalog exceeds its supported bounds.');
    const routes = new Set<string>();
    for (const row of value.serving.models) {
      if (!object(row) || typeof row.provider_id !== 'string' || typeof row.model_id !== 'string' || typeof row.route_id !== 'string' || row.route_id !== `${row.provider_id}:${row.model_id}` || routes.has(row.route_id)
        || typeof row.active !== 'boolean' || !object(row.policy) || !object(row.capacity) || !object(row.pressure) || !object(row.cache) || typeof row.draining !== 'boolean') invalid('A configured local model has an invalid serving identity or observation.');
      if (row.policy.enabled !== undefined && typeof row.policy.enabled !== 'boolean') invalid('A configured model has an invalid adaptive serving policy.');
      routes.add(row.route_id);
    }
  }
  return value as RuntimeControlState;
}

export async function getRuntimeOptimization(signal?: AbortSignal, learningOffset = 0): Promise<RuntimeControlObservation> {
  if (!Number.isSafeInteger(learningOffset) || learningOffset < 0 || learningOffset > 127) throw new ChatClientError('Choose a learner page offset from 0 through 127.', { kind: 'validation', retryable: false });
  const scope = await account(signal);
  const result = await read(api.get<unknown>(`${ROOT}?learning_offset=${learningOffset}`, { ...OPTIONS, signal, headers: authHeaders() }), scope.token, signal);
  const runtime = state(result, scope);
  const limits = runtime.learning.limits;
  if (!limits || limits.partition_offset !== learningOffset || !Number.isSafeInteger(limits.total_partitions) || Number(limits.total_partitions) < 0 || Number(limits.total_partitions) > 128
    || !Number.isSafeInteger(limits.returned_partitions) || Number(limits.returned_partitions) < 0 || Number(limits.returned_partitions) > 10 || limits.returned_partitions !== runtime.learning.partitions?.length
    || typeof limits.has_more_partitions !== 'boolean' || limits.has_more_partitions !== (learningOffset + Number(limits.returned_partitions) < Number(limits.total_partitions))) invalid('The learner page does not match its requested offset or canonical bounds.');
  return { state: runtime, scope, observedAt: Date.now() };
}

export async function changeRuntimeOptimization(observed: RuntimeControlObservation, change: RuntimeControlChange, signal?: AbortSignal): Promise<RuntimeControlObservation> {
  current(observed.scope.token, signal);
  const scope = await account(signal, observed.scope);
  if (scope.role !== 'admin') throw new ChatClientError('An administrator account is required to change runtime policy.', { kind: 'authorization', retryable: false });
  if (Date.now() - observed.observedAt > 60000) throw new ChatClientError('The runtime observation is stale. Refresh and apply your change again.', { kind: 'conflict', code: 'runtime_observation_stale', retryable: false });
  const maximum = change.serving?.max_effective_concurrency;
  const route = change.serving_route_id === undefined ? observed.state.serving : observed.state.serving.models?.find(row => row.route_id === change.serving_route_id);
  if (!route) throw new ChatClientError('The selected local model is no longer in the observed serving catalog. Refresh its current state.', { kind: 'conflict', code: 'runtime_serving_route_changed', retryable: false });
  if (maximum !== undefined && (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > Math.min(32, route.capacity?.operator_max_concurrency ?? 0))) throw new ChatClientError('Choose a concurrency limit within the observed operator capacity.', { kind: 'validation', retryable: false });
  const result = await read(api.patch<unknown>(ROOT, { expected_version: observed.state.policy_version, ...change }, { ...OPTIONS, signal, headers: authHeaders() }), scope.token, signal);
  return { state: state(result, scope), scope, observedAt: Date.now() };
}

function partitionBinding(observed: RuntimeControlObservation, partition: RuntimeLearningPartition): { partitionId: string; modelDigest: string; taskClass: string; version: number; scopeId: string } {
  const found = observed.state.learning.partitions?.find(row => row.partition_id === partition.partition_id);
  if (!found || !HASH.test(String(partition.partition_id)) || !HASH.test(String(partition.model_selection_digest)) || !Number.isSafeInteger(partition.state_version) || Number(partition.state_version) < 1
    || found.state_version !== partition.state_version || found.model_selection_digest !== partition.model_selection_digest || found.task_class !== partition.task_class) throw new ChatClientError('The selected learner identity or version is not current. Refresh and select it again.', { kind: 'conflict', code: 'runtime_partition_changed', retryable: false });
  return { partitionId: partition.partition_id!, modelDigest: partition.model_selection_digest!, taskClass: identity(partition.task_class), version: partition.state_version!, scopeId: identity(observed.state.learning.scope_id) };
}
export function canManageRuntimePartition(observed: RuntimeControlObservation, partition: RuntimeLearningPartition): boolean {
  try { partitionBinding(observed, partition); return true; } catch { return false; }
}
async function adminAccount(observed: RuntimeControlObservation, signal?: AbortSignal, purpose = 'manage learner checkpoints'): Promise<AccountScope> {
  current(observed.scope.token, signal);
  const scope = await account(signal, observed.scope);
  if (scope.role !== 'admin') throw new ChatClientError(`An administrator account is required to ${purpose}.`, { kind: 'authorization', retryable: false });
  if (Date.now() - observed.observedAt > 60000) throw new ChatClientError('The runtime observation is stale. Refresh before continuing.', { kind: 'conflict', code: 'runtime_observation_stale', retryable: false });
  return scope;
}

/** Preview identity only. The canonical engine validates the numeric state and its digest on import. */
export function validateRuntimeCheckpoint(value: unknown, observed: RuntimeControlObservation, partition: RuntimeLearningPartition): RuntimeLearningCheckpoint {
  const binding = partitionBinding(observed, partition);
  if (!object(value) || value.schema_version !== 'skeleton.runtime.learning.checkpoint.v1' || value.feature_schema !== 'skeleton.runtime.learning.features.v1'
    || value.tenant_id !== observed.scope.tenantId || value.scope_id !== binding.scopeId || value.partition_id !== binding.partitionId || value.task_class !== binding.taskClass || value.model_selection_digest !== binding.modelDigest
    || !Number.isSafeInteger(value.state_version) || Number(value.state_version) < 1 || !HASH.test(String(value.state_digest)) || !HASH.test(String(value.checkpoint_digest)) || value.source_snapshot_digest !== '' && !HASH.test(String(value.source_snapshot_digest)) || !object(value.state)) throw new ChatClientError('This checkpoint does not match the selected tenant, task, model and feature schema, or its identity is incomplete.', { kind: 'validation', code: 'runtime_checkpoint_binding_invalid', retryable: false });
  let nodes = 0;
  const bounded = (item: unknown, depth: number): void => {
    if (++nodes > 100000 || depth > 24 || typeof item === 'number' && !Number.isFinite(item) || typeof item === 'string' && item.length > 4096) invalid('The learner checkpoint contains invalid or excessive state.');
    if (Array.isArray(item)) item.forEach(child => bounded(child, depth + 1));
    else if (object(item)) Object.values(item).forEach(child => bounded(child, depth + 1));
  };
  bounded(value, 0);
  if (new TextEncoder().encode(JSON.stringify(value)).byteLength > MAX_RUNTIME_CHECKPOINT_BYTES) throw new ChatClientError('Choose a learner checkpoint no larger than 256 KiB.', { kind: 'validation', retryable: false });
  return value as RuntimeLearningCheckpoint;
}
export function parseRuntimeCheckpoint(text: string, observed: RuntimeControlObservation, partition: RuntimeLearningPartition): RuntimeLearningCheckpoint {
  if (new TextEncoder().encode(text).byteLength > MAX_RUNTIME_CHECKPOINT_BYTES) throw new ChatClientError('Choose a learner checkpoint no larger than 256 KiB.', { kind: 'validation', retryable: false });
  let value: unknown;
  try { value = JSON.parse(text); } catch { throw new ChatClientError('Choose a valid JSON learner checkpoint exported by this studio.', { kind: 'validation', retryable: false }); }
  return validateRuntimeCheckpoint(value, observed, partition);
}
export async function exportRuntimeCheckpoint(observed: RuntimeControlObservation, partition: RuntimeLearningPartition, signal?: AbortSignal): Promise<RuntimeLearningCheckpointFile> {
  const binding = partitionBinding(observed, partition);
  const scope = await adminAccount(observed, signal);
  const result = await read(api.get<unknown>(`${ROOT}/learning/partitions/${encodeURIComponent(binding.partitionId)}/checkpoint?expected_state_version=${binding.version}`, { ...OPTIONS, maxResponseChars: 768 * 1024, signal, headers: authHeaders() }), scope.token, signal);
  if (!object(result) || result.schema_version !== 'skeleton.ai.runtime_learning_checkpoint.v1' || result.actor_id !== scope.principalId || result.tenant_id !== scope.tenantId || result.partition_id !== binding.partitionId || typeof result.checkpoint_json !== 'string' || result.checkpoint !== undefined) invalid('The learner export does not match the authorized account, partition and canonical file format.');
  const checkpoint = parseRuntimeCheckpoint(result.checkpoint_json, observed, partition);
  if (checkpoint.state_version !== binding.version) invalid('The learner export does not match the observed partition version.');
  return { checkpoint, checkpointJson: result.checkpoint_json };
}
export async function changeRuntimePartition(observed: RuntimeControlObservation, partition: RuntimeLearningPartition, action: RuntimeLearningAction, checkpointJson?: string, signal?: AbortSignal): Promise<{ observation: RuntimeControlObservation; receipt: Fields }> {
  const binding = partitionBinding(observed, partition);
  const scope = await adminAccount(observed, signal);
  if ((action === 'import') !== (typeof checkpointJson === 'string')) throw new ChatClientError('Only checkpoint import accepts and requires the original JSON file text.', { kind: 'validation', retryable: false });
  if (action === 'import') parseRuntimeCheckpoint(checkpointJson!, observed, partition);
  const result = await read(api.post<unknown>(`${ROOT}/learning/partitions/${encodeURIComponent(binding.partitionId)}/checkpoint`, {
    action, expected_policy_version: observed.state.policy_version, expected_state_version: binding.version,
    model_selection_digest: binding.modelDigest, ...(action === 'import' ? { checkpoint_json: checkpointJson } : {}),
  }, { ...OPTIONS, maxResponseChars: 384 * 1024, signal, headers: authHeaders() }), scope.token, signal);
  if (!object(result) || result.schema_version !== 'skeleton.ai.runtime_learning_control.v1' || result.actor_id !== scope.principalId || result.tenant_id !== scope.tenantId || result.partition_id !== binding.partitionId || !object(result.receipt)) invalid('The learner action receipt does not match its authorized partition.');
  const receipt = result.receipt;
  const mutation = receipt.learning_checkpoint;
  if (receipt.schema_version !== 'skeleton.runtime.control.event.v1' || receipt.tenant_id !== scope.tenantId || receipt.version !== observed.state.policy_version + 1 || !HASH.test(String(receipt.receipt_digest))
    || !object(mutation) || mutation.partition_id !== binding.partitionId || mutation.action !== action || mutation.model_selection_digest !== binding.modelDigest || mutation.previous_state_version !== binding.version
    || !Number.isSafeInteger(mutation.state_version) || Number(mutation.state_version) <= binding.version || !HASH.test(String(mutation.previous_state_digest)) || !HASH.test(String(mutation.state_digest))
    || mutation.checkpoint_digest !== null && !HASH.test(String(mutation.checkpoint_digest))) invalid('The learner action audit receipt does not bind the requested action, model and versions. Refresh canonical state before trying again.');
  const runtime = state(result.runtime, scope);
  if (runtime.policy_version < Number(receipt.version)) invalid('The runtime observation precedes the learner action receipt. Refresh current state.');
  if (result.partition !== undefined && (!object(result.partition) || result.partition.partition_id !== binding.partitionId || result.partition.model_selection_digest !== binding.modelDigest || result.partition.state_version !== mutation.state_version)) invalid('The learner action result disagrees with its immutable audit receipt.');
  return { observation: { state: runtime, scope, observedAt: Date.now() }, receipt };
}

export async function retryRuntimeMaintenanceTask(observed: RuntimeControlObservation, task: RuntimeMaintenanceTask, signal?: AbortSignal): Promise<{ observation: RuntimeControlObservation; result: { task_id: string; source_digest: string; state: 'ready' | 'retry_wait'; attempts: number; deduplicated: boolean } }> {
  const maintenance = observed.state.maintenance;
  const found = maintenance.recent_tasks?.find(row => row.task_id === task.task_id);
  if (maintenance.available !== true || maintenance.coordination?.state !== 'observed' || maintenance.status?.coordination_state !== 'synchronized') throw new ChatClientError('Healthy maintenance coordination must be observed before retrying a task. Refresh current state.', { kind: 'unavailable', retryable: false });
  if (!found || task.retryable !== true || found.retryable !== true || !HASH.test(String(task.task_id)) || !HASH.test(String(task.source_digest))
    || found.source_digest !== task.source_digest || found.attempts !== task.attempts || !Number.isSafeInteger(task.attempts) || Number(task.attempts) < 0 || Number(task.attempts) > 1000000) throw new ChatClientError('The failed maintenance task or its attempt binding is stale. Refresh current state before retrying.', { kind: 'conflict', code: 'runtime_maintenance_task_changed', retryable: false });
  const scope = await adminAccount(observed, signal, 'retry failed maintenance tasks');
  const result = await read(api.post<unknown>(`${ROOT}/maintenance/tasks/${encodeURIComponent(task.task_id!)}/retry`, {
    source_digest: task.source_digest, expected_attempts: task.attempts,
  }, { ...OPTIONS, maxResponseChars: 384 * 1024, signal, headers: authHeaders() }), scope.token, signal);
  if (!object(result) || result.schema_version !== 'skeleton.ai.runtime_maintenance_retry.v1' || result.actor_id !== scope.principalId || result.tenant_id !== scope.tenantId || result.task_id !== task.task_id || !object(result.result)) invalid('The maintenance retry does not match the authorized account and task.');
  const retry = result.result;
  if (retry.task_id !== task.task_id || retry.source_digest !== task.source_digest || retry.attempts !== task.attempts || !['ready', 'retry_wait'].includes(String(retry.state)) || typeof retry.deduplicated !== 'boolean') invalid('The maintenance retry result does not bind the requested source and attempt count. Refresh current state before continuing.');
  return { observation: { state: state(result.runtime, scope), scope, observedAt: Date.now() }, result: retry as { task_id: string; source_digest: string; state: 'ready' | 'retry_wait'; attempts: number; deduplicated: boolean } };
}
