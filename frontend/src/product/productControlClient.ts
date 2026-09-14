import api, { ApiResult } from '../utils/apiClient';

export type ExecutorBinding = {
  capability_id: string;
  action: string;
  name: string;
  version: number;
  effect_class: 'query' | 'state' | 'external';
  replay_safe: boolean;
};

export type ContentStoreStats = { chunks: number; bytes: number; manifests: number };
export type ReceiptVaultStats = { receipts: number; results: ContentStoreStats; version: number };

export type ActionReadiness = {
  capability_id: string;
  action: string;
  state: 'native_ready' | 'governed_unbound' | 'unsafe' | 'policy_gap';
  policy_present: boolean;
  executor_bound: boolean;
  replay_safe: boolean;
  effect_class: 'query' | 'state' | 'external' | null;
  executor_name: string | null;
  executor_version: number | null;
  provenance_ready: boolean;
  blockers: string[];
};

export type ReadinessReport = {
  canonical_actions: number;
  ready_actions: number;
  ready_pct: number;
  governed_unbound: number;
  unsafe_actions: number;
  policy_gaps: number;
  actions: ActionReadiness[];
  attestation_sha256: string;
};

export type AssuranceInvariant = {
  id: string;
  severity: 'hard' | 'warning';
  passed: boolean;
  detail: string;
};

export type AssuranceReport = {
  posture: 'healthy' | 'degraded' | 'blocked';
  hard_failures: number;
  warnings: number;
  native_coverage_pct: number;
  readiness_pct: number;
  invariants: AssuranceInvariant[];
  attestation_sha256: string;
};

export type ControlPlaneStatus = {
  policy_version: number;
  policy_bootstrap_enabled: boolean;
  kernel: { capabilities: Array<{ id: string; pillar: string; critical: boolean }>; critical_ids: string[] };
  governance: { charters: Array<{ id: string; domain: string; amendments: number; rules: Array<{ id: string; action: string; min_weight: number; requires_quorum: boolean }> }>; edicts: unknown[] };
  executors: {
    bound: number;
    bindings: ExecutorBinding[];
    coverage: { canonical_actions: number; bound_actions: number; coverage_pct: number; missing: Array<{ capability_id: string; action: string }> };
  };
  readiness: ReadinessReport;
  assurance: AssuranceReport;
  receipts: ReceiptVaultStats;
  lifecycle: { operations: number; states: Record<string, number>; evidence_gaps: number; anomalies: number };
  operations: { capabilities: number; pending_operations: number; outbox_capacity_remaining: number; idempotency_records: number; audit_sequence: number; audit_head: string | null };
};

export type PendingOperation = {
  operation_id: string; capability_id: string; pillar: string; domain: string; action: string; principal: string;
  outbox_seq: number; admitted_at: string; idempotency_key: string | null; executor_bound: boolean;
};
export type PendingOperationResponse = { count: number; operations: PendingOperation[] };
export type AuditEntry = { seq: number; ts: string; kind: string; seal: string; principal: string; route: string; detail: string; prev_hash: string; hash: string };
export type ExecutionReceipt = {
  operation_id: string; capability_id: string; action: string; executor: string; executor_version: number;
  effect_class: 'query' | 'state' | 'external'; replay_safe: boolean; input_artifact_manifest_id: string;
  completed_at: string; result_artifact_id: string; result_sha256: string; result_summary: Record<string, unknown>;
  legacy_inline_result: Record<string, unknown> | null;
};
export type DispatchFailure = { outbox_seq: number; operation_id: string; executor: string; error: string };
export type DispatchReport = {
  attempted: number;
  confirmed: number[];
  deferred: number[];
  unbound: number[];
  failed: DispatchFailure[];
  remaining: number;
};
export type OperationAdmission = { operation_id: string; capability_id: string; pillar: string; outbox_seq: number; admitted_at: string; audit_hash: string };
export type AdmitOperationInput = { capability_id: string; domain: string; action: string; principal: string; actor_weight: number; payload: Record<string, unknown>; quorum_approved?: boolean; idempotency_key?: string };

const ROOT = '/api/admin/ops/product-control';
function tokenQuery(token: string): string { return token ? `?token=${encodeURIComponent(token)}` : ''; }
function tokenQueryWith(token: string, params: Record<string, string | number>): string {
  const query = new URLSearchParams(); if (token) query.set('token', token);
  Object.entries(params).forEach(([key, value]) => query.set(key, String(value)));
  const encoded = query.toString(); return encoded ? `?${encoded}` : '';
}

export function getProductControlStatus(token = '', signal?: AbortSignal): Promise<ApiResult<ControlPlaneStatus>> {
  return api.get<ControlPlaneStatus>(`${ROOT}/status${tokenQuery(token)}`, { signal, cacheKey: 'product-control-status', cacheTtlMs: 5_000 });
}
export function getPendingProductOperations(token = '', signal?: AbortSignal): Promise<ApiResult<PendingOperationResponse>> {
  return api.get<PendingOperationResponse>(`${ROOT}/pending${tokenQuery(token)}`, { signal, cacheKey: 'product-control-pending', cacheTtlMs: 2_000 });
}
export function getProductAuditHistory(token = '', limit = 50, signal?: AbortSignal): Promise<ApiResult<{ entries: AuditEntry[] }>> {
  return api.get<{ entries: AuditEntry[] }>(`${ROOT}/audit${tokenQueryWith(token, { limit })}`, { signal, cacheKey: `product-control-audit-${limit}`, cacheTtlMs: 2_000 });
}
export function getExecutionReceipts(token = '', limit = 50, signal?: AbortSignal): Promise<ApiResult<{ receipts: ExecutionReceipt[] }>> {
  return api.get<{ receipts: ExecutionReceipt[] }>(`${ROOT}/receipts${tokenQueryWith(token, { limit })}`, { signal, cacheKey: `product-control-receipts-${limit}`, cacheTtlMs: 2_000 });
}
export function getExecutionResult(operationId: string, token = '', signal?: AbortSignal): Promise<ApiResult<Record<string, unknown>>> {
  return api.get<Record<string, unknown>>(`${ROOT}/receipt/${encodeURIComponent(operationId)}/result${tokenQuery(token)}`, { signal, cacheKey: `product-control-result-${operationId}`, cacheTtlMs: 30_000 });
}
export function executeProductOperation(seq: number, token = '', signal?: AbortSignal): Promise<ApiResult<{ outbox_seq: number; confirmed: boolean; status: string }>> {
  return api.post(`${ROOT}/execute/${seq}${tokenQuery(token)}`, {}, { signal, retries: 0 });
}
export function executePendingProductOperations(token = '', limit = 32, signal?: AbortSignal): Promise<ApiResult<DispatchReport>> {
  return api.post<DispatchReport>(`${ROOT}/execute-pending${tokenQueryWith(token, { limit })}`, {}, { signal, retries: 0 });
}
export function admitProductOperation(input: AdmitOperationInput, token = '', signal?: AbortSignal): Promise<ApiResult<OperationAdmission>> {
  const idempotencyKey = input.idempotency_key || `${input.capability_id}:${input.action}:${Date.now()}`;
  return api.post<OperationAdmission>(`${ROOT}/admit${tokenQuery(token)}`, { ...input, idempotency_key: idempotencyKey }, { signal, idempotencyKey, retries: 2 });
}
