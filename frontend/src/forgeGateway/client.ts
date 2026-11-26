/**
 * Typed client for the backend forge gateway. The gateway authenticates the
 * signed-in user and seals requests to the engine server-side, so this client
 * never sees or sends an engine seal (`x-gf-seal`).
 */
import api, { type ApiResult } from '../utils/apiClient';
import type { BuildAck, BuildView, Playtest } from './model';

export const GATEWAY_PREFIX = '/api/forge-gateway';

export interface GatewayStatus {
  schema: string;
  engine_configured: boolean;
  seal_configured: boolean;
  builds_per_minute: number | null;
  operations: string[];
}

export interface StartBuildInput {
  brief: string;
  playtest?: Playtest;
  idempotencyKey: string;
  signal?: AbortSignal;
}

export function startGameBuild(input: StartBuildInput): Promise<ApiResult<BuildAck>> {
  return api.post<BuildAck>(
    `${GATEWAY_PREFIX}/game/build`,
    { brief: input.brief.trim(), playtest: input.playtest ?? 'auto' },
    { signal: input.signal, timeoutMs: 30_000, retries: 1, idempotencyKey: input.idempotencyKey, serverDedupeVerified: true },
  );
}

export function getGameBuild(executionId: string, signal?: AbortSignal): Promise<ApiResult<BuildView>> {
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(executionId)) {
    return Promise.resolve({ ok: false, status: 404, data: null, error: 'build not found', rid: null });
  }
  return api.get<BuildView>(`${GATEWAY_PREFIX}/game/build/${encodeURIComponent(executionId)}`, { signal, timeoutMs: 15_000, retries: 1 });
}

export function getGatewayStatus(signal?: AbortSignal): Promise<ApiResult<GatewayStatus>> {
  return api.get<GatewayStatus>(`${GATEWAY_PREFIX}/status`, { signal, timeoutMs: 10_000 });
}
