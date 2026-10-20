import { authHeaders, getAuthToken } from '../auth/gameforgeAuth';
import api, { type ApiResult } from '../utils/apiClient';
import { ChatClientError, chatApiError } from './chatErrors';

type Fields = Record<string, unknown>;
export type RuntimeControlState = {
  schema_version: 'skeleton.ai.runtime_control.v1';
  policy_version: number;
  reconciliation?: { state?: 'applied' | 'pending'; error_code?: string | null };
  actor_id: string;
  tenant_id: string;
  serving: {
    available?: boolean;
    policy?: { enabled?: boolean; min_effective_concurrency?: number; max_effective_concurrency?: number };
    capacity?: { operator_max_concurrency?: number; effective_concurrency?: number; background_limit?: number; active_interactive?: number; active_background?: number; queued_interactive?: number; queued_background?: number };
    pressure?: { level?: string; reason?: string; latency_ewma_ms?: number; queue_wait_ewma_ms?: number; failure_ewma?: number; resource?: Fields; samples?: number };
    cache?: { entries?: number; bytes?: number; max_bytes?: number; evictions?: number; expirations?: number; singleflight_active?: number; singleflight_hits?: number };
    draining?: boolean;
  };
  learning: {
    available?: boolean;
    policy?: { enabled?: boolean; min_samples?: number };
    totals_health?: 'healthy' | 'quarantined';
    totals?: { outcomes?: number; completed?: number; degraded?: number; failed?: number; cancelled?: number; resource_failures?: number; telemetry_errors?: number; provider_attempts?: number } | null;
    partitions?: { partition_id?: string; task_class?: string; samples?: number; optimizer_steps?: number; readiness?: string; quarantined?: boolean; uncertainty?: number; prediction_error?: number }[];
    limits?: { returned_partitions?: number; returned_outcomes?: number };
  };
  maintenance: {
    available?: boolean;
    policy?: { enabled?: boolean; augmentation_enabled?: boolean };
    status?: { state?: string; active_tasks?: number; foreground_requests?: number; last_run_ns?: number | null; next_run_ns?: number | null; last_reason?: string };
    queued_tasks?: number;
    recent_tasks?: { task_id?: string; kind?: string; state?: string; attempts?: number; failures?: number; updated_at_ns?: number }[];
  };
  ratchet: { available: boolean; baseline?: Fields | null };
};

type AccountScope = { token: string; tenantId: string; principalId: string; role: string };
export type RuntimeControlObservation = { state: RuntimeControlState; scope: AccountScope; observedAt: number };
export type RuntimeControlAction = 'trim_cache' | 'clear_cache' | 'drain' | 'resume';
export type RuntimeControlChange = {
  serving?: { enabled?: boolean; max_effective_concurrency?: number };
  learning?: { enabled: boolean };
  maintenance?: { enabled?: boolean; augmentation_enabled?: boolean };
  action?: RuntimeControlAction;
};
const ROOT = '/api/ai/runtime-control';
const OPTIONS = { timeoutMs: 15000, retries: 0, maxResponseChars: 256 * 1024 };

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
  return value as RuntimeControlState;
}

export async function getRuntimeOptimization(signal?: AbortSignal): Promise<RuntimeControlObservation> {
  const scope = await account(signal);
  const result = await read(api.get<unknown>(ROOT, { ...OPTIONS, signal, headers: authHeaders() }), scope.token, signal);
  return { state: state(result, scope), scope, observedAt: Date.now() };
}

export async function changeRuntimeOptimization(observed: RuntimeControlObservation, change: RuntimeControlChange, signal?: AbortSignal): Promise<RuntimeControlObservation> {
  current(observed.scope.token, signal);
  const scope = await account(signal, observed.scope);
  if (scope.role !== 'admin') throw new ChatClientError('An administrator account is required to change runtime policy.', { kind: 'authorization', retryable: false });
  if (Date.now() - observed.observedAt > 60000) throw new ChatClientError('The runtime observation is stale. Refresh and apply your change again.', { kind: 'conflict', code: 'runtime_observation_stale', retryable: false });
  const maximum = change.serving?.max_effective_concurrency;
  if (maximum !== undefined && (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > Math.min(32, observed.state.serving.capacity?.operator_max_concurrency ?? 0))) throw new ChatClientError('Choose a concurrency limit within the observed operator capacity.', { kind: 'validation', retryable: false });
  const result = await read(api.patch<unknown>(ROOT, { expected_version: observed.state.policy_version, ...change }, { ...OPTIONS, signal, headers: authHeaders() }), scope.token, signal);
  return { state: state(result, scope), scope, observedAt: Date.now() };
}
