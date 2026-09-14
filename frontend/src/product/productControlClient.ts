import api, { ApiResult } from '../utils/apiClient';

export type ControlPlaneStatus = {
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

export function getProductControlStatus(token = '', signal?: AbortSignal): Promise<ApiResult<ControlPlaneStatus>> {
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  return api.get<ControlPlaneStatus>(`${ROOT}/status${query}`, {
    signal,
    cacheKey: 'product-control-status',
    cacheTtlMs: 5_000,
  });
}

export function admitProductOperation(
  input: AdmitOperationInput,
  token = '',
  signal?: AbortSignal,
): Promise<ApiResult<OperationAdmission>> {
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  const idempotencyKey = input.idempotency_key || `${input.capability_id}:${input.action}:${Date.now()}`;
  return api.post<OperationAdmission>(`${ROOT}/admit${query}`, { ...input, idempotency_key: idempotencyKey }, {
    signal,
    idempotencyKey,
    retries: 2,
  });
}
