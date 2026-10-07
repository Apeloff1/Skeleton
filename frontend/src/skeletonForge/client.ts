/**
 * Thin typed client over the Skeleton GameForge routes. Uses the shared
 * apiClient (retries, timeouts, circuit breaker, breadcrumbs).
 */
import api, { type ApiResult } from '../utils/apiClient';
import type { Beat, CockpitResult, ComposeResult, EraRow, GenerationRow, RunPayload, RunRequest } from './types';

export const SKELETON_API = '/api/skeleton';

export function fetchBeats(signal?: AbortSignal): Promise<ApiResult<{ beats: Beat[] }>> {
  return api.get(`${SKELETON_API}/beats`, { signal, timeoutMs: 10000, cacheKey: 'skeleton:beats', cacheTtlMs: 300000 });
}

export function fetchEras(signal?: AbortSignal): Promise<ApiResult<{ eras: EraRow[]; count: number }>> {
  return api.get(`${SKELETON_API}/eras`, { signal, timeoutMs: 15000, cacheKey: 'skeleton:eras', cacheTtlMs: 300000 });
}

export function fetchGenerations(signal?: AbortSignal): Promise<ApiResult<{ generations: GenerationRow[]; count: number }>> {
  return api.get(`${SKELETON_API}/generations`, { signal, timeoutMs: 10000, cacheKey: 'skeleton:generations', cacheTtlMs: 300000 });
}

export function composeVision(vision: string, signal?: AbortSignal): Promise<ApiResult<ComposeResult>> {
  return api.post(`${SKELETON_API}/compose`, { vision: vision.slice(0, 4000) }, { signal, timeoutMs: 12000, retries: 0 });
}

export function runForge(req: RunRequest, signal?: AbortSignal): Promise<ApiResult<RunPayload>> {
  return api.post(`${SKELETON_API}/run`, { ...req, include_files: false }, { signal, timeoutMs: 180000, retries: 0 });
}

export function sendCockpit(command: string, signal?: AbortSignal): Promise<ApiResult<CockpitResult>> {
  return api.post(`${SKELETON_API}/cockpit`, { command }, { signal, timeoutMs: 20000, retries: 0 });
}

/** Human error text from an ApiResult (FastAPI `detail` aware). */
export function errorText(r: ApiResult<any> | null | undefined): string {
  if (!r) return 'No response';
  const d = r.data as any;
  const detail = d && typeof d === 'object' ? d.detail : null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  if (r.error === 'circuit_open') return 'The forge is cooling down after repeated failures — try again shortly.';
  if (r.status === 0) return r.error === 'aborted' ? 'Cancelled' : 'Backend unreachable';
  return r.error || `HTTP ${r.status}`;
}
