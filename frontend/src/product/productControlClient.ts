import api, { ApiResult } from '../utils/apiClient';

export type ControlPlaneStatus = {
  policy_version: number;
  policy_bootstrap_enabled: boolean;
  kernel: {
    capabilities: Array<{ id: string; pillar: string; critical: boolean }>;
    critical_ids: string[];
  };
  governance: {
    charters: Array<{
      id: string;
      domain: string;
      amendments: number;
      rules: Array<{ id: string; action: string; min_weight: number; requires_quorum: boolean }>;
    }>;
    edicts: unknown[];
  };
  operations: {
    capabilities: number;
    pending_operations: number;
    outbox_capacity_remaining: number;
    idempotency_records: number;
    audit_sequence: number;
    audit_head: string | null;
  };
};

export type PendingOperation = {
  operation_id: string;
  capability_id: string;
  pillar: string;
  domain: string;
  action: string;
  principal: string;
  outbox_seq: number;
  admitted_at: string;
  idempotency_key: string | null;
};

export type PendingOperationResponse = {
  count: number;
  operations: PendingOperation[];
};

export type AuditEntry = {
  seq: number;
  ts: string;
  kind: string;
  seal: string;
  principal: string;
  route: string;
  detail: string;
  prev_hash: string;
  hash: string;
};

export type OperationAdmission = {
  operation_id: string;
  capability_id: string;
  pillar: string;
  outbox_seq: number;
  admitted_at: string;
  audit_hash: string;
};

export type AdmitOperationInput = {
  capability_id: string;
  domain: string;
  action: string;
  principal: string;
  actor_weight: number;
  payload: Record<string, unknown>;
  quorum_approved?: boolean;
  idempotency_key?: string;
};

const ROOT = '/api/admin/ops/product-control';

function tokenQuery(token: string): string {
  return token ? `?token=${encodeURIComponent(token)}` : '';
}

function tokenQueryWith(token: string, params: Record<string, string | number>): string {
  const query = new URLSearchParams();
  if (token) query.set('token', token);
  Object.entries(params).forEach(([key, value]) => query.set(key, String(value)));
  const encoded = query.toString();
  return encoded ? `?${encoded}` : '';
}

export function getProductControlStatus(token = '', signal?: AbortSignal): Promise<ApiResult<ControlPlaneStatus>> {
  return api.get<ControlPlaneStatus>(`${ROOT}/status${tokenQuery(token)}`, {
    signal,
    cacheKey: 'product-control-status',
    cacheTtlMs: 5_000,
  });
}

export function getPendingProductOperations(token = '', signal?: AbortSignal): Promise<ApiResult<PendingOperationResponse>> {
  return api.get<PendingOperationResponse>(`${ROOT}/pending${tokenQuery(token)}`, {
    signal,
    cacheKey: 'product-control-pending',
    cacheTtlMs: 2_000,
  });
}

export function getProductAuditHistory(token = '', limit = 50, signal?: AbortSignal): Promise<ApiResult<{ entries: AuditEntry[] }>> {
  return api.get<{ entries: AuditEntry[] }>(`${ROOT}/audit${tokenQueryWith(token, { limit })}`, {
    signal,
    cacheKey: `product-control-audit-${limit}`,
    cacheTtlMs: 2_000,
  });
}

export function admitProductOperation(
  input: AdmitOperationInput,
  token = '',
  signal?: AbortSignal,
): Promise<ApiResult<OperationAdmission>> {
  const idempotencyKey = input.idempotency_key || `${input.capability_id}:${input.action}:${Date.now()}`;
  return api.post<OperationAdmission>(
    `${ROOT}/admit${tokenQuery(token)}`,
    { ...input, idempotency_key: idempotencyKey },
    { signal, idempotencyKey, retries: 2 },
  );
}
