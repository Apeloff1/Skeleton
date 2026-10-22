import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import api, { type ApiResult } from '../utils/apiClient';
import { ChatClientError, chatApiError } from './chatErrors';

type Fields = Record<string, unknown>;
export type RuntimePolicyValues = { [name: string]: number | boolean | undefined };
export type RuntimePolicySection = 'serving' | 'learning' | 'maintenance';
export type RuntimePolicyField = { type: 'boolean' | 'integer' | 'number'; min?: number; max?: number; unit: string; description: string };
export type RuntimePolicyControls = {
  schema_version: 'skeleton.ai.runtime_policy_controls.v1'; max_patch_bytes: number;
  serving: RuntimePolicySectionControls & { route_limits?: Record<string, RuntimeServingLimits>; global_limits?: RuntimeServingLimits };
  learning: RuntimePolicySectionControls; maintenance: RuntimePolicySectionControls;
};
export type RuntimeServingLimits = { max_concurrency: number; max_queue_size: number };
export type RuntimePolicySectionControls = { scope: 'host' | 'tenant'; fields: Record<string, RuntimePolicyField>; constraints: string[]; available: boolean };
export type RuntimeLearningPartition = {
  partition_id?: string; task_class?: string; model_selection_digest?: string; state_version?: number;
  samples?: number; fresh_samples?: number; optimizer_steps?: number; readiness?: string;
  quarantined?: boolean; uncertainty?: number; prediction_error?: number; confidence_reasons?: string[];
  drift?: { active?: boolean; score?: number; events?: number; cooldown_remaining?: number; fast_loss?: number; slow_loss?: number; last_prequential_loss?: number; prequential_count?: number };
  last_healthy?: { available?: boolean; observations?: number; optimizer_step?: number; checkpoint_digest?: string };
  rollback_count?: number; generation?: number;
  source_provenance?: { latest_source_digest?: string; recent_source_count?: number; source_switches?: number; latest_source_samples?: number };
  optimizer_cost?: { terminal_updates?: number; replay_updates?: number; maintenance_updates?: number; total_updates?: number };
  /** Optional read-only projection; its renderer validates it independently. */
  reference_explanation?: unknown;
};
export type RuntimeServingState = {
  available?: boolean;
  provider_id?: string; model_id?: string; model_digest?: string; route_id?: string; active?: boolean;
  policy?: RuntimePolicyValues & { enabled?: boolean; min_effective_concurrency?: number; max_effective_concurrency?: number };
  capacity?: { operator_max_concurrency?: number; operator_max_queue_size?: number; effective_concurrency?: number; background_limit?: number; active_interactive?: number; active_background?: number; queued_interactive?: number; queued_background?: number; per_tenant_active_limit?: number; per_tenant_queue_limit?: number; effective_queue_limit?: number };
  pressure?: { level?: string; reason?: string; latency_ewma_ms?: number; queue_wait_ewma_ms?: number; failure_ewma?: number; resource?: Fields; samples?: number };
  cache?: { entries?: number; bytes?: number; max_bytes?: number; evictions?: number; expirations?: number; singleflight_active?: number; singleflight_hits?: number; singleflight_tenants?: number; largest_tenant_singleflight_waiters?: number };
  fairness?: { active_tenants?: number; queued_tenants?: number; largest_tenant_active?: number; largest_tenant_queued?: number; rotations?: number; aged_background_admissions?: number; tenant_limit_rejections?: number; memory_shed_rejections?: number; load_shed_rejections?: number; oldest_interactive_wait_ms?: number; oldest_background_wait_ms?: number; max_observed_queue_wait_ms?: number };
  draining?: boolean;
  execution_contract?: unknown;
  execution_contract_error?: unknown;
};
export type RuntimeMaintenanceTask = {
  task_id?: string; scope_id?: string; kind?: string; state?: string; attempts?: number; failures?: number; updated_at_ns?: number;
  source_digest?: string; retryable?: boolean; retry_reason?: string | null;
  scheduling?: unknown;
};
export type RuntimeMaintenanceCircuit = { kind?: string; state?: 'open' | 'half_open' | 'closed'; failures?: number; open_until_ns?: number; generation?: number; last_failure_digest?: string; last_source_digest?: string; last_task_id?: string; last_failure_at_ns?: number; resettable?: boolean; reset_reason?: string | null };
export type RuntimeControlState = {
  schema_version: 'skeleton.ai.runtime_control.v1';
  policy_version: number;
  reconciliation?: { state?: 'applied' | 'pending'; error_code?: string | null };
  actor_id: string;
  tenant_id: string;
  policy_controls?: RuntimePolicyControls;
  serving: RuntimeServingState & { models?: RuntimeServingState[] };
  learning: {
    available?: boolean;
    policy?: RuntimePolicyValues & { enabled?: boolean; min_samples?: number };
    totals_health?: 'healthy' | 'quarantined';
    totals?: { outcomes?: number; completed?: number; degraded?: number; failed?: number; cancelled?: number; resource_failures?: number; telemetry_errors?: number; provider_attempts?: number } | null;
    scope_id?: string;
    partitions?: RuntimeLearningPartition[];
    limits?: { partition_offset?: number; total_partitions?: number; has_more_partitions?: boolean; returned_partitions?: number; returned_outcomes?: number };
  };
  maintenance: {
    available?: boolean;
    policy?: RuntimePolicyValues & { enabled?: boolean; augmentation_enabled?: boolean };
    status?: { state?: string; active_tasks?: number; foreground_requests?: number; last_run_ns?: number | null; next_run_ns?: number | null; last_reason?: string; coordination_state?: 'synchronized' | 'unavailable'; coordination_error?: string | null };
    queued_tasks?: number;
    recent_tasks?: RuntimeMaintenanceTask[];
    circuits?: RuntimeMaintenanceCircuit[];
    ownership?: { owner_id?: string; host_id?: string; state?: string; heartbeat_ns?: number; foreground_requests?: number; physical_tasks?: number };
    leases?: { resource_id?: string; scope_id?: string; owner_id?: string; fencing_token?: number; state?: string; heartbeat_ns?: number; lease_until_ns?: number; drained_at_ns?: number | null }[];
    recovery?: { blocked_tasks?: number; clock_jump_count?: number; last_clock_jump_reason?: string | null };
    coordination?: { state?: 'observed' | 'degraded'; error_code?: string | null };
    quiescence?: { host_foreground_requests?: number; registered_host_owners?: number; observation?: string; last_admission?: { observed_at_ns?: number; permitted?: boolean; reason?: string; owners_examined?: number; stale_owners?: number; recent_activity_owners?: number; minimum_quiet_ns?: number | null; required_quiet_ns?: number; maximum_heartbeat_age_ns?: number; maximum_owner_heartbeat_ms?: number } | null; last_presence_repair?: { observed_at_ns?: number; examined?: number; retired?: number; unproven?: number } | null };
    telemetry?: { observed_at_ns?: number; host_now_ns?: number; age_ns?: number; quiet_ns?: number; serving_pressure_ppm?: number; cpu_free_ppm?: number; memory_free_ppm?: number; gpu_free_ppm?: number | null; pending_interactive_requests?: number; active_background_workers?: number; power_saving?: boolean; online?: boolean; telemetry_digest?: string; admission_reason?: string } | null;
    chunk_results?: { retained?: number; reserved?: number; reusable_unverified?: number; shared_retained?: number; maximum?: number; backpressure?: boolean };
    acknowledgements?: { pending?: number; failed_attempts?: number; next_retry_ns?: number | null; last_error?: string | null; callback_available?: boolean };
    handler_registry?: unknown;
    queue_summary?: unknown;
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
  serving?: RuntimePolicyValues;
  learning?: RuntimePolicyValues;
  maintenance?: RuntimePolicyValues;
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
export const MAX_RUNTIME_DATASET_BYTES = 1024 * 1024;
export type RuntimeLearningDatasetFilters = { partitionId?: string; includeUntrained: boolean; limit: number };
export type RuntimeLearningDatasetFile = {
  datasetJson: string;
  dataset: {
    schema_version: 'skeleton.runtime.learning.dataset.v1'; tenant_id: string; scope_id: string; feature_schema: string;
    feature_names: string[]; target_names: string[]; rows: Fields[]; row_count: number; scanned_rows: number;
    omitted_rows: { execution_id?: string; outcome_id?: string; reason?: string }[];
    filters: { partition_id: string | null; include_untrained: boolean };
    next_cursor: string | null; has_more: boolean; dataset_digest: string;
    watermark: { observed_at: string; execution_id: string } | null;
    retention: { retained_outcomes?: number; outcome_max_age_days?: number };
    limitations: string[]; limits: { max_rows: number; max_json_bytes: number; max_cursor_bytes: number };
  };
};
const ROOT = '/api/ai/runtime-control';
const OPTIONS = { timeoutMs: 15000, retries: 0, maxResponseChars: 256 * 1024 };
const HASH = /^[a-f0-9]{64}$/;
const MAX_CIRCUIT_GENERATION = 9_000_000_000_000_000;

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
  // These optional projections never participate in control/authority checks.
  // Their bounded renderers reject malformed metadata locally so a broken
  // explanation cannot disable otherwise valid recovery or policy controls.
  const displayOnly = new WeakMap<object, Set<string>>();
  const diagnostics = (owner: unknown, keys: string[]) => { if (object(owner)) displayOnly.set(owner, new Set(keys)); };
  diagnostics(value.serving, ['execution_contract', 'execution_contract_error']);
  if (Array.isArray(value.serving.models)) value.serving.models.forEach(row => diagnostics(row, ['execution_contract', 'execution_contract_error']));
  if (Array.isArray(value.learning.partitions)) value.learning.partitions.forEach(row => diagnostics(row, ['reference_explanation']));
  diagnostics(value.maintenance, ['handler_registry', 'queue_summary']);
  if (Array.isArray(value.maintenance.recent_tasks)) value.maintenance.recent_tasks.forEach(row => diagnostics(row, ['scheduling']));
  let nodes = 0;
  const bounded = (item: unknown, depth: number): void => {
    if (++nodes > 12000 || depth > 12) invalid('The runtime observation exceeds its supported bounds.');
    if (typeof item === 'number' && !Number.isFinite(item) || typeof item === 'string' && item.length > 4096) invalid('The runtime observation contains invalid telemetry.');
    if (Array.isArray(item)) { if (item.length > 256) invalid('The runtime observation contains too many records.'); item.forEach(child => bounded(child, depth + 1)); }
    else if (object(item)) Object.entries(item).forEach(([key, child]) => { if (!displayOnly.get(item)?.has(key)) bounded(child, depth + 1); });
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
  if (value.maintenance.circuits !== undefined) {
    if (!Array.isArray(value.maintenance.circuits) || value.maintenance.circuits.length > 64 || value.maintenance.circuits.some(row => !object(row))) invalid('The maintenance circuit observation is invalid.');
    for (const row of value.maintenance.circuits as Fields[]) if (row.resettable !== undefined && typeof row.resettable !== 'boolean' || row.resettable === true && (typeof row.kind !== 'string' || !Number.isSafeInteger(row.generation) || Number(row.generation) < 1 || Number(row.generation) >= MAX_CIRCUIT_GENERATION || !HASH.test(String(row.last_failure_digest)) || !HASH.test(String(row.last_source_digest)))) invalid('A resettable circuit is missing its exact generation and source-bound failure.');
  }
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
  if (value.policy_controls !== undefined) {
    const controls = value.policy_controls;
    if (!object(controls) || controls.schema_version !== 'skeleton.ai.runtime_policy_controls.v1' || !Number.isSafeInteger(controls.max_patch_bytes) || Number(controls.max_patch_bytes) < 1 || Number(controls.max_patch_bytes) > 16384) invalid('The runtime policy field catalog is invalid.');
    for (const section of ['serving', 'learning', 'maintenance']) {
      const control = controls[section];
      if (!object(control) || control.scope !== (section === 'learning' ? 'tenant' : 'host') || typeof control.available !== 'boolean' || !object(control.fields) || Object.keys(control.fields).length > 64 || !Array.isArray(control.constraints) || control.constraints.length > 16 || control.constraints.some(item => typeof item !== 'string' || item.length > 512)) invalid('The runtime policy section catalog is invalid.');
      for (const [name, field] of Object.entries(control.fields)) {
        if (!/^[a-z][a-z0-9_]{0,79}$/.test(name) || !object(field) || !['boolean', 'integer', 'number'].includes(String(field.type)) || typeof field.unit !== 'string' || field.unit.length > 64 || typeof field.description !== 'string' || field.description.length > 1024) invalid('A runtime policy field is invalid.');
        if (field.type !== 'boolean' && (typeof field.min !== 'number' || !Number.isFinite(field.min) || typeof field.max !== 'number' || !Number.isFinite(field.max) || field.min > field.max)) invalid('A runtime policy field has invalid numeric bounds.');
      }
      for (const limits of [control.global_limits, ...Object.values(object(control.route_limits) ? control.route_limits : {})]) {
        if (limits !== undefined && (!object(limits) || !Number.isSafeInteger(limits.max_concurrency) || Number(limits.max_concurrency) < 0 || Number(limits.max_concurrency) > 32 || !Number.isSafeInteger(limits.max_queue_size) || Number(limits.max_queue_size) < 0 || Number(limits.max_queue_size) > 65536)) invalid('The serving operator limits are invalid.');
      }
    }
  }
  return value as RuntimeControlState;
}

/** The catalog describes fields; existing server owners remain the policy authority. */
export function runtimePolicyFieldBounds(field: RuntimePolicyField, section: RuntimePolicySection, name: string, controls: RuntimePolicyControls, routeId?: string): { min?: number; max?: number } {
  let maximum = field.max;
  if (section === 'serving') {
    const limits = routeId ? controls.serving.route_limits?.[routeId] : controls.serving.global_limits;
    const ceiling = ['min_effective_concurrency', 'max_effective_concurrency', 'background_max_concurrency', 'max_active_per_tenant'].includes(name) ? limits?.max_concurrency : name === 'max_queued_per_tenant' ? limits?.max_queue_size : undefined;
    if (ceiling !== undefined) maximum = Math.min(maximum ?? ceiling, ceiling);
  }
  return { min: field.min, max: maximum };
}
export function validateRuntimePolicyChange(observed: RuntimeControlObservation, change: RuntimeControlChange): void {
  const controls = observed.state.policy_controls;
  for (const section of ['serving', 'learning', 'maintenance'] as const) {
    const values = change[section];
    if (values === undefined) continue;
    if (!Object.keys(values).length) throw new ChatClientError('Choose at least one changed policy field.', { kind: 'validation', retryable: false });
    const fields = controls?.[section];
    if (fields && !fields.available || observed.state[section].available === false) throw new ChatClientError(`The ${section} policy is unavailable. Refresh its current capability.`, { kind: 'unavailable', retryable: false });
    for (const [name, value] of Object.entries(values)) {
      const field = fields?.fields[name];
      if (!field) {
        const legacyBoolean = name === 'enabled' || section === 'maintenance' && name === 'augmentation_enabled';
        if (controls || !legacyBoolean && !(section === 'serving' && name === 'max_effective_concurrency') || legacyBoolean && typeof value !== 'boolean') throw new ChatClientError('This field is not declared editable by the observed runtime.', { kind: 'validation', retryable: false });
        continue;
      }
      const bounds = runtimePolicyFieldBounds(field, section, name, controls!, change.serving_route_id);
      const valid = field.type === 'boolean' ? typeof value === 'boolean' : typeof value === 'number' && Number.isFinite(value) && (field.type !== 'integer' || Number.isSafeInteger(value)) && value >= bounds.min! && value <= bounds.max!;
      if (!valid) throw new ChatClientError(`${name.replaceAll('_', ' ')} must fit its observed ${field.type === 'boolean' ? 'switch type' : `${bounds.min}–${bounds.max} ${field.unit} bound`}.`, { kind: 'validation', retryable: false });
    }
    const currentPolicy = section === 'serving' && change.serving_route_id ? observed.state.serving.models?.find(row => row.route_id === change.serving_route_id)?.policy : observed.state[section].policy;
    const merged: RuntimePolicyValues = { ...currentPolicy, ...values };
    if (section === 'serving' && (typeof merged.min_effective_concurrency === 'number' && typeof merged.max_effective_concurrency === 'number' && merged.min_effective_concurrency > merged.max_effective_concurrency || typeof merged.memory_low_watermark === 'number' && typeof merged.memory_high_watermark === 'number' && merged.memory_low_watermark >= merged.memory_high_watermark)) throw new ChatClientError('Minimum concurrency must not exceed its maximum, and the low memory watermark must remain below the high watermark.', { kind: 'validation', retryable: false });
    if (section === 'maintenance' && typeof merged.initial_backoff_ms === 'number' && typeof merged.maximum_backoff_ms === 'number' && merged.initial_backoff_ms > merged.maximum_backoff_ms) throw new ChatClientError('Initial backoff must not exceed maximum backoff.', { kind: 'validation', retryable: false });
  }
  if (controls && new TextEncoder().encode(JSON.stringify({ expected_version: observed.state.policy_version, ...change })).byteLength > controls.max_patch_bytes) throw new ChatClientError('This policy patch exceeds the observed request bound. Apply fewer fields together.', { kind: 'validation', retryable: false });
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
  if (maximum !== undefined && (typeof maximum !== 'number' || !Number.isSafeInteger(maximum) || maximum < 1 || maximum > Math.min(32, route.capacity?.operator_max_concurrency ?? 0))) throw new ChatClientError('Choose a concurrency limit within the observed operator capacity.', { kind: 'validation', retryable: false });
  validateRuntimePolicyChange(observed, change);
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

function datasetFile(text: string, observed: RuntimeControlObservation, filters: RuntimeLearningDatasetFilters): RuntimeLearningDatasetFile {
  if (new TextEncoder().encode(text).byteLength > MAX_RUNTIME_DATASET_BYTES) invalid('The numeric dataset page exceeds its 1 MiB bound.');
  let page: unknown;
  try { page = JSON.parse(text); } catch { invalid('The numeric dataset page is not valid canonical JSON.'); }
  if (!object(page) || page.schema_version !== 'skeleton.runtime.learning.dataset.v1' || page.tenant_id !== observed.scope.tenantId || page.scope_id !== observed.state.learning.scope_id || page.feature_schema !== 'skeleton.runtime.learning.features.v1'
    || !object(page.filters) || page.filters.partition_id !== (filters.partitionId ?? null) || page.filters.include_untrained !== filters.includeUntrained
    || !Array.isArray(page.rows) || page.rows.length > filters.limit || !Number.isSafeInteger(page.row_count) || page.row_count !== page.rows.length || !Number.isSafeInteger(page.scanned_rows) || Number(page.scanned_rows) < page.rows.length || Number(page.scanned_rows) > filters.limit
    || !Array.isArray(page.omitted_rows) || page.omitted_rows.length > 256 || page.omitted_rows.some(row => !object(row)) || page.rows.length + page.omitted_rows.length !== page.scanned_rows
    || !HASH.test(String(page.dataset_digest)) || typeof page.has_more !== 'boolean' || (page.next_cursor !== null && typeof page.next_cursor !== 'string') || page.has_more !== (typeof page.next_cursor === 'string' && page.next_cursor.length > 0)
    || !object(page.retention) || !object(page.limits) || page.limits.max_rows !== 256 || page.limits.max_json_bytes !== MAX_RUNTIME_DATASET_BYTES || !Number.isSafeInteger(page.limits.max_cursor_bytes) || Number(page.limits.max_cursor_bytes) < 1 || Number(page.limits.max_cursor_bytes) > 6144
    || !Array.isArray(page.feature_names) || page.feature_names.length !== 12 || page.feature_names.some(item => typeof item !== 'string' || item.length > 160)
    || !Array.isArray(page.target_names) || page.target_names.length !== 3 || page.target_names.some(item => typeof item !== 'string' || item.length > 160)
    || !Array.isArray(page.limitations) || page.limitations.length > 32 || page.limitations.some(item => typeof item !== 'string' || item.length > 2048)) invalid('The numeric dataset page does not match its authorized tenant, filters and bounded schema.');
  if (page.next_cursor !== null && new TextEncoder().encode(String(page.next_cursor)).byteLength > Number(page.limits.max_cursor_bytes)) invalid('The numeric dataset cursor exceeds its server-declared bound.');
  if (page.watermark !== null && (!object(page.watermark) || typeof page.watermark.observed_at !== 'string' || typeof page.watermark.execution_id !== 'string')) invalid('The numeric dataset watermark is invalid.');
  for (const row of page.rows as Fields[]) if (!object(row) || !Array.isArray(row.features) || row.features.length !== 12 || !Array.isArray(row.targets) || row.targets.length !== 3 || [...row.features, ...row.targets].some(value => typeof value !== 'number' || !Number.isFinite(value)) || row.provenance_verified !== true || typeof row.trained_online !== 'boolean' || !filters.includeUntrained && row.trained_online !== true || filters.partitionId && row.partition_id !== filters.partitionId) invalid('A numeric dataset row is missing finite features, targets or verified canonical provenance for the requested filters.');
  let nodes = 0;
  const bounded = (value: unknown, depth: number): void => {
    if (++nodes > 100000 || depth > 16 || typeof value === 'number' && !Number.isFinite(value) || typeof value === 'string' && value.length > 8192) invalid('The numeric dataset contains excessive or invalid metadata.');
    if (Array.isArray(value)) { if (value.length > 1024) invalid('The numeric dataset contains too many metadata entries.'); value.forEach(item => bounded(item, depth + 1)); }
    else if (object(value)) Object.values(value).forEach(item => bounded(item, depth + 1));
  };
  bounded(page, 0);
  return { datasetJson: text, dataset: page as RuntimeLearningDatasetFile['dataset'] };
}
export async function exportRuntimeLearningDataset(observed: RuntimeControlObservation, filters: RuntimeLearningDatasetFilters, cursor?: string, signal?: AbortSignal): Promise<RuntimeLearningDatasetFile> {
  if (!Number.isSafeInteger(filters.limit) || filters.limit < 1 || filters.limit > 256 || typeof filters.includeUntrained !== 'boolean' || filters.partitionId !== undefined && !HASH.test(filters.partitionId) || cursor !== undefined && (!cursor || new TextEncoder().encode(cursor).byteLength > 6144)) throw new ChatClientError('Choose valid numeric dataset filters and a bounded server cursor.', { kind: 'validation', retryable: false });
  if (observed.state.learning.available === false) throw new ChatClientError('The tenant learner is unavailable. Refresh its current state before exporting.', { kind: 'unavailable', retryable: false });
  const scope = await adminAccount(observed, signal, 'export the tenant numeric learning dataset');
  const query = new URLSearchParams({ limit: String(filters.limit), include_untrained: String(filters.includeUntrained) });
  if (filters.partitionId) query.set('partition_id', filters.partitionId);
  if (cursor) query.set('cursor', cursor);
  const result = await read(api.get<unknown>(`${ROOT}/learning/dataset?${query.toString()}`, { ...OPTIONS, maxResponseChars: 3 * 1024 * 1024, signal, headers: authHeaders() }), scope.token, signal);
  if (!object(result) || result.schema_version !== 'skeleton.ai.runtime_learning_dataset.v1' || result.actor_id !== scope.principalId || result.tenant_id !== scope.tenantId || typeof result.dataset_json !== 'string') invalid('The numeric dataset export does not match the authorized account and canonical file format.');
  return datasetFile(result.dataset_json, observed, filters);
}
export async function authorizeRuntimeDatasetDownload(observed: RuntimeControlObservation, file: RuntimeLearningDatasetFile, signal?: AbortSignal): Promise<void> {
  await adminAccount(observed, signal, 'download the tenant numeric learning dataset');
  datasetFile(file.datasetJson, observed, { partitionId: file.dataset.filters.partition_id ?? undefined, includeUntrained: file.dataset.filters.include_untrained, limit: 256 });
}

export async function resetRuntimeMaintenanceCircuit(observed: RuntimeControlObservation, circuit: RuntimeMaintenanceCircuit, signal?: AbortSignal): Promise<{ observation: RuntimeControlObservation; result: { kind: string; generation: number; deduplicated: boolean } }> {
  const maintenance = observed.state.maintenance;
  const found = maintenance.circuits?.find(row => row.kind === circuit.kind);
  if (maintenance.available !== true || maintenance.coordination?.state !== 'observed' || maintenance.status?.coordination_state !== 'synchronized') throw new ChatClientError('Healthy maintenance coordination must be observed before resetting a circuit.', { kind: 'unavailable', retryable: false });
  if (!found || circuit.resettable !== true || found.resettable !== true || typeof circuit.kind !== 'string' || !/^[a-z][a-z0-9_]{0,100}$/.test(circuit.kind) || !Number.isSafeInteger(circuit.generation) || Number(circuit.generation) < 1 || Number(circuit.generation) >= MAX_CIRCUIT_GENERATION || !HASH.test(String(circuit.last_failure_digest)) || !HASH.test(String(circuit.last_source_digest))
    || found.generation !== circuit.generation || found.last_failure_digest !== circuit.last_failure_digest || found.last_source_digest !== circuit.last_source_digest) throw new ChatClientError('The circuit generation or source-bound failure changed. Refresh and review current recovery eligibility.', { kind: 'conflict', code: 'runtime_maintenance_circuit_changed', retryable: false });
  const scope = await adminAccount(observed, signal, 'reset a scoped maintenance circuit');
  const value = await read(api.post<unknown>(`${ROOT}/maintenance/circuits/${encodeURIComponent(circuit.kind)}/reset`, { expected_generation: circuit.generation, expected_failure_digest: circuit.last_failure_digest, source_digest: circuit.last_source_digest }, { ...OPTIONS, maxResponseChars: 384 * 1024, signal, headers: authHeaders() }), scope.token, signal);
  if (!object(value) || value.schema_version !== 'skeleton.ai.runtime_maintenance_circuit_reset.v1' || value.actor_id !== scope.principalId || value.tenant_id !== scope.tenantId || value.kind !== circuit.kind || !object(value.result)) invalid('The maintenance circuit receipt does not match its authorized account and kind.');
  const result = value.result;
  if (result.kind !== circuit.kind || result.generation !== Number(circuit.generation) + 1 || result.source_digest !== circuit.last_source_digest || result.failure_digest !== circuit.last_failure_digest || result.state !== 'closed' || result.failures !== 0 || result.open_until_ns !== 0 || typeof result.deduplicated !== 'boolean') invalid('The circuit reset result does not bind the observed generation, failure and source. Refresh canonical state before continuing.');
  return { observation: { state: state(value.runtime, scope), scope, observedAt: Date.now() }, result: result as { kind: string; generation: number; deduplicated: boolean } };
}
