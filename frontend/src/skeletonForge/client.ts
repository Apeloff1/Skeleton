/**
 * Thin typed client over the Skeleton GameForge routes. Uses the shared
 * apiClient (retries, timeouts, circuit breaker, breadcrumbs).
 */
import api, { type ApiResult } from '../utils/apiClient';
import type { Beat, CockpitResult, ComposeResult, EraRow, GenerationRow, GenreControlProfile, RunPayload, RunRequest } from './types';

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

/** Read-only semantic action profiles; requests are bounded and abortable. */
export function fetchGenreControls(genre: string, signal?: AbortSignal): Promise<ApiResult<GenreControlProfile>> {
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(genre)) {
    return Promise.resolve({ ok: false, status: 400, error: 'Invalid creator genre' } as ApiResult<GenreControlProfile>);
  }
  return api.get(`${SKELETON_API}/controls/genres/${encodeURIComponent(genre)}`, {
    signal, timeoutMs: 10000, retries: 0,
    cacheKey: `skeleton:controls:${genre}`, cacheTtlMs: 300000,
  });
}

/** Seven-stage historical planning is preview-only: no project files are written. */
export interface ConductorPreviewResult {
  ok: boolean;
  mode: string;
  completed: string[];
  artifacts: string[];
  artifact_count: number;
  byte_total: number;
  manifest?: unknown;
}

export function previewHistoricalConductor(
  request: { title: string; pitch: string; genre: string; pillars: string[] },
  signal?: AbortSignal,
): Promise<ApiResult<ConductorPreviewResult>> {
  return api.post(`${SKELETON_API}/conductor/preview`, {
    ...request, era: 'HOUSE_ERA', target: 'bundle',
    target_minutes: 15, budget_bytes: 1000000, regions: 5,
  }, { signal, timeoutMs: 15000, retries: 0 });
}

/** Public taskset metadata only: no local model inference is triggered. */
export interface JeevesGameQualityCatalog {
  schema: string;
  taskset_id: string;
  scorer_id: string;
  taskset_sha256: string;
  task_count: number;
  categories: string[];
  dimensions: string[];
  model_quality_certified: false;
  inference_started: false;
  local_gguf_required_for_run: true;
}

export function fetchJeevesGameQualityCatalog(signal?: AbortSignal): Promise<ApiResult<JeevesGameQualityCatalog>> {
  return api.get(`${SKELETON_API}/jeeves/game-quality`, {
    signal, retries: 0, timeoutMs: 10000,
    cacheKey: 'skeleton:jeeves-game-quality', cacheTtlMs: 300000,
  });
}

export function composeVision(vision: string, signal?: AbortSignal): Promise<ApiResult<ComposeResult>> {
  return api.post(`${SKELETON_API}/compose`, { vision: vision.slice(0, 4000) }, { signal, timeoutMs: 12000, retries: 0 });
}

export function runForge(req: RunRequest, signal?: AbortSignal): Promise<ApiResult<RunPayload>> {
  // Explicit native verification can boot both the generated world and a
  // separate authored playable scene. The ordinary request keeps its original
  // 3-minute bound; native proof has an independently bounded 8-minute cap.
  const nativeProof = req.playtest === 'auto' || req.playtest === 'require';
  return api.post(`${SKELETON_API}/run`, { ...req, include_files: false }, {
    signal, timeoutMs: nativeProof ? 480000 : 180000, retries: 0,
  });
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
