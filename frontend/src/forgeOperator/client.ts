/**
 * Typed forge-operator client over two backends:
 *   • application (`API_BASE` via shared apiClient) — `/api/skeleton/*`
 *   • Skeleton engine (`SKELETON_API_BASE`) — sealed `/api/v1/gameforge/*`
 *
 * Pure URL/body/header helpers stay free of RN so node:test can load them
 * (with thin stubs for apiClient / apiBase). Network calls reuse apiClient
 * retries, timeouts and circuit breaker; absolute engine URLs are fine
 * because apiClient already accepts paths that start with `http`.
 */
import api, { type ApiResult } from '../utils/apiClient';
import { SKELETON_API_BASE } from '../../utils/apiBase';
import { toOperatorError, type OperatorError } from './errors';
import type {
  Beat,
  BuildPlan,
  ComposeResult,
  EngineIntakeRequest,
  EngineRunPayload,
  EngineRunRequest,
  EraRow,
  GenerationRow,
  PlanRequest,
  WalkPreview,
} from './types';
import type { CockpitResult, RunPayload, RunRequest } from '../skeletonForge/types';

export const APP_SKELETON_API = '/api/skeleton';
export const ENGINE_API_V1 = '/api/v1';

export type SealHeaders = {
  /** Minted `x-gf-seal` — never hardcoded; caller supplies. */
  seal?: string | null;
  /** Optional charter actor weight (`x-gf-actor-weight`). */
  actorWeight?: number | string | null;
};

export type ClientOpts = {
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
  retries?: number;
};

/** Join `/api/skeleton` with a relative route (`eras` or `/eras`). */
export function skeletonPath(route: string): string {
  const suffix = route.startsWith('/') ? route : `/${route}`;
  return `${APP_SKELETON_API}${suffix}`;
}

/**
 * Absolute engine URL: `base` + `/api/v1/...`.
 * Pass `SKELETON_API_BASE` (or any override) as `base` — helpers stay pure.
 */
export function enginePath(base: string, route: string): string {
  const root = String(base || '').replace(/\/+$/, '');
  let path = route.startsWith('/') ? route : `/${route}`;
  if (!path.startsWith('/api/')) {
    path = `${ENGINE_API_V1}${path.startsWith('/') ? path : `/${path}`}`;
  }
  return `${root}${path}`;
}

/** Merge optional seal / actor-weight into request headers (no secrets inlined). */
export function mergeSealHeaders(
  seal: SealHeaders | null | undefined,
  extra?: Record<string, string> | null,
): Record<string, string> {
  const out: Record<string, string> = { ...(extra || {}) };
  const token = seal?.seal == null ? '' : String(seal.seal).trim();
  if (token) out['x-gf-seal'] = token;
  if (seal?.actorWeight != null && seal.actorWeight !== '') {
    out['x-gf-actor-weight'] = String(seal.actorWeight);
  }
  return out;
}

/** Shape a plan/walk body; drops empty optional fields. */
export function buildPlanBody(req: PlanRequest = {}): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (req.vision != null && req.vision !== '') body.vision = String(req.vision).slice(0, 4000);
  if (req.era != null && req.era !== '') body.era = req.era;
  if (req.blend && Array.isArray(req.blend) && req.blend.length >= 2) {
    body.blend = [String(req.blend[0]), String(req.blend[1])];
  }
  if (typeof req.t === 'number' && Number.isFinite(req.t)) body.t = req.t;
  return body;
}

/** Body for `POST /api/v1/gameforge/run` (defaults match the engine). */
export function buildRunBody(req: EngineRunRequest): Record<string, unknown> {
  const body: Record<string, unknown> = {
    vision: String(req.vision || '').slice(0, 4000),
    target: req.target,
    playtest: req.playtest,
    repair_mode: req.repair_mode,
    include_files: req.include_files === true,
  };
  if (req.era) body.era = req.era;
  if (req.archetype) body.archetype = req.archetype;
  if (req.answers && typeof req.answers === 'object') body.answers = req.answers;
  return body;
}

/** Body for `POST /api/v1/gameforge/intake`. */
export function buildIntakeBody(req: EngineIntakeRequest): Record<string, unknown> {
  const body: Record<string, unknown> = {
    answers: req.answers && typeof req.answers === 'object' ? req.answers : {},
    target: req.target,
    playtest: req.playtest,
    repair_mode: req.repair_mode,
  };
  if (req.archetype) body.archetype = req.archetype;
  return body;
}

/** Fold an ApiResult failure into an OperatorError (sealed routes by default). */
export function operatorErrorFromApi(
  result: Pick<ApiResult<unknown>, 'ok' | 'status' | 'error' | 'data' | 'rid'> | null | undefined,
  opts: { sealed?: boolean; sealPresent?: boolean; ops?: boolean } = {},
): OperatorError | null {
  if (!result || result.ok) return null;
  return toOperatorError(
    { status: result.status, error: result.error, data: result.data, rid: result.rid },
    opts,
  );
}

// ── Application backend (`API_BASE` /api/skeleton/*) ───────────────────

export function fetchEras(opts: ClientOpts = {}): Promise<ApiResult<{ eras: EraRow[]; count: number }>> {
  return api.get(skeletonPath('/eras'), {
    signal: opts.signal,
    timeoutMs: opts.timeoutMs ?? 15000,
    headers: opts.headers,
    cacheKey: 'forge-op:eras',
    cacheTtlMs: 300000,
  });
}

export function fetchBeats(opts: ClientOpts = {}): Promise<ApiResult<{ beats: Beat[] }>> {
  return api.get(skeletonPath('/beats'), {
    signal: opts.signal,
    timeoutMs: opts.timeoutMs ?? 10000,
    headers: opts.headers,
    cacheKey: 'forge-op:beats',
    cacheTtlMs: 300000,
  });
}

export function fetchGenerations(opts: ClientOpts = {}): Promise<ApiResult<{ generations: GenerationRow[]; count: number }>> {
  return api.get(skeletonPath('/generations'), {
    signal: opts.signal,
    timeoutMs: opts.timeoutMs ?? 10000,
    headers: opts.headers,
    cacheKey: 'forge-op:generations',
    cacheTtlMs: 300000,
  });
}

export function composeVision(vision: string, opts: ClientOpts = {}): Promise<ApiResult<ComposeResult>> {
  return api.post(
    skeletonPath('/compose'),
    { vision: String(vision || '').slice(0, 4000) },
    { signal: opts.signal, timeoutMs: opts.timeoutMs ?? 12000, headers: opts.headers, retries: opts.retries ?? 0 },
  );
}

export function runAppForge(req: RunRequest, opts: ClientOpts = {}): Promise<ApiResult<RunPayload>> {
  return api.post(
    skeletonPath('/run'),
    { ...req, include_files: false },
    { signal: opts.signal, timeoutMs: opts.timeoutMs ?? 180000, headers: opts.headers, retries: opts.retries ?? 0 },
  );
}

export function planBuild(req: PlanRequest = {}, opts: ClientOpts = {}): Promise<ApiResult<BuildPlan>> {
  return api.post(
    skeletonPath('/plan'),
    buildPlanBody(req),
    { signal: opts.signal, timeoutMs: opts.timeoutMs ?? 30000, headers: opts.headers, retries: opts.retries ?? 0 },
  );
}

export function walkPreview(req: PlanRequest = {}, opts: ClientOpts = {}): Promise<ApiResult<WalkPreview>> {
  return api.post(
    skeletonPath('/walk'),
    buildPlanBody(req),
    { signal: opts.signal, timeoutMs: opts.timeoutMs ?? 60000, headers: opts.headers, retries: opts.retries ?? 0 },
  );
}

export function sendAppCockpit(command: string, opts: ClientOpts = {}): Promise<ApiResult<CockpitResult>> {
  return api.post(
    skeletonPath('/cockpit'),
    { command },
    { signal: opts.signal, timeoutMs: opts.timeoutMs ?? 20000, headers: opts.headers, retries: opts.retries ?? 0 },
  );
}

// ── Skeleton engine (`SKELETON_API_BASE` /api/v1/gameforge/*) ───────────

export function engineRun(
  req: EngineRunRequest,
  seal?: SealHeaders | null,
  opts: ClientOpts = {},
): Promise<ApiResult<EngineRunPayload>> {
  const headers = mergeSealHeaders(seal, opts.headers);
  return api.post(
    enginePath(SKELETON_API_BASE, '/api/v1/gameforge/run'),
    buildRunBody(req),
    {
      signal: opts.signal,
      timeoutMs: opts.timeoutMs ?? 180000,
      headers,
      retries: opts.retries ?? 0,
    },
  );
}

export function engineIntake(
  req: EngineIntakeRequest,
  seal?: SealHeaders | null,
  opts: ClientOpts = {},
): Promise<ApiResult<EngineRunPayload>> {
  const headers = mergeSealHeaders(seal, opts.headers);
  return api.post(
    enginePath(SKELETON_API_BASE, '/api/v1/gameforge/intake'),
    buildIntakeBody(req),
    {
      signal: opts.signal,
      timeoutMs: opts.timeoutMs ?? 180000,
      headers,
      retries: opts.retries ?? 0,
    },
  );
}
