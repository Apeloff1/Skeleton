/**
 * Turn a failed read into a user-facing explanation.
 *
 * Screens used to swallow failed loads and fall through to their empty state
 * ("No saved worlds yet"), which tells the user something false. This maps the
 * transport outcome (ApiResult, a fetch Response, or a thrown error) to a
 * short, honest message and whether retrying can help. Pure and testable.
 */
import { t } from './strings';

export type LoadFailureKind =
  | 'offline' | 'timeout' | 'unauthorised' | 'forbidden' | 'not-found'
  | 'rate-limited' | 'unavailable' | 'invalid-response' | 'unknown';

export interface LoadFailure {
  kind: LoadFailureKind;
  /** Short sentence for the notice body. */
  message: string;
  /** Retrying the same request may succeed. */
  retryable: boolean;
  /** HTTP status when known (0 = no response). */
  status: number | null;
  /** Server detail, only when it is a short plain string safe to show. */
  detail: string | null;
}

export interface FailureInput {
  status?: number | null;
  error?: unknown;
  detail?: unknown;
}

const MAX_DETAIL = 160;

function safeDetail(detail: unknown): string | null {
  if (typeof detail !== 'string') return null;
  const clean = detail.replace(/\s+/g, ' ').trim();
  if (!clean || /<\/?[a-z][\s\S]*>/i.test(clean)) return null; // never echo HTML error pages
  return clean.length > MAX_DETAIL ? `${clean.slice(0, MAX_DETAIL - 1)}…` : clean;
}

function errorText(error: unknown): string {
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object' && 'message' in error) return String((error as { message: unknown }).message ?? '');
  return '';
}

export function classifyFailure(input: FailureInput): LoadFailureKind {
  const status = typeof input.status === 'number' ? input.status : null;
  const text = errorText(input.error).toLowerCase();
  if (status === 401) return 'unauthorised';
  if (status === 403) return 'forbidden';
  if (status === 404 || status === 410) return 'not-found';
  if (status === 429) return 'rate-limited';
  if (status === 408 || status === 504 || /timed? ?out|timeout|aborted/.test(text)) return 'timeout';
  if (status !== null && status >= 500) return 'unavailable';
  if (status === 0 || /network|failed to fetch|offline|load failed|econnrefused/.test(text)) return 'offline';
  if (/json|unexpected token|invalid response|malformed/.test(text)) return 'invalid-response';
  return 'unknown';
}

const MESSAGE: Record<LoadFailureKind, Parameters<typeof t>[0]> = {
  offline: 'load.offline',
  timeout: 'load.timeout',
  unauthorised: 'load.unauthorised',
  forbidden: 'load.forbidden',
  'not-found': 'load.notFound',
  'rate-limited': 'load.rateLimited',
  unavailable: 'load.unavailable',
  'invalid-response': 'load.invalid',
  unknown: 'load.unknown',
};

const RETRYABLE: ReadonlySet<LoadFailureKind> = new Set(['offline', 'timeout', 'rate-limited', 'unavailable', 'unknown', 'invalid-response']);

export function describeLoadFailure(input: FailureInput): LoadFailure {
  const kind = classifyFailure(input);
  return {
    kind,
    message: t(MESSAGE[kind]),
    retryable: RETRYABLE.has(kind),
    status: typeof input.status === 'number' ? input.status : null,
    detail: safeDetail(input.detail),
  };
}

/** From the shared api client's ApiResult ({ ok, status, error }). */
export function failureFromResult(r: { ok: boolean; status: number; error?: string | null; data?: unknown }): LoadFailure | null {
  if (r.ok) return null;
  const body = r.data as { detail?: unknown } | null | undefined;
  return describeLoadFailure({ status: r.status, error: r.error, detail: body && typeof body === 'object' ? body.detail : r.error });
}

/**
 * For raw fetch(): resolves to the parsed JSON when the response is OK and the
 * body parses, otherwise throws a LoadFailureError carrying the description.
 */
export class LoadFailureError extends Error {
  readonly failure: LoadFailure;
  constructor(failure: LoadFailure) {
    super(failure.detail ?? failure.message);
    this.name = 'LoadFailureError';
    this.failure = failure;
  }
}

export async function readJsonOrThrow<T = unknown>(res: { ok: boolean; status: number; json: () => Promise<unknown> }): Promise<T> {
  let body: unknown = null;
  let parseError: unknown = null;
  try { body = await res.json(); } catch (e) { parseError = e; }
  if (!res.ok) {
    const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null;
    throw new LoadFailureError(describeLoadFailure({ status: res.status, detail }));
  }
  if (parseError) throw new LoadFailureError(describeLoadFailure({ status: res.status, error: 'invalid response' }));
  return body as T;
}

/** Any thrown value → LoadFailure (keeps the classification of LoadFailureError). */
export function failureFromError(error: unknown): LoadFailure {
  if (error instanceof LoadFailureError) return error.failure;
  // apiController's ApiError carries { status, body, code }; status 0 means no response.
  if (error && typeof error === 'object' && typeof (error as { status?: unknown }).status === 'number') {
    const e = error as { status: number; body?: unknown; code?: unknown };
    const detail = e.body && typeof e.body === 'object' ? (e.body as { detail?: unknown }).detail : null;
    const status = e.code === 'timeout' ? 408 : e.status;
    return describeLoadFailure({ status, error, detail });
  }
  return describeLoadFailure({ error });
}
