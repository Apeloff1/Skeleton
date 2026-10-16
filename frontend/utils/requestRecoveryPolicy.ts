/**
 * Network recovery policy shared by the frontend request transport.
 * Requests that may mutate server state are never replayed implicitly.
 * This pure module has no dependency on React, storage or providers.
 */
export const MAX_RETRIES = 3;
export const MIN_TIMEOUT_MS = 250;
export const MAX_TIMEOUT_MS = 30_000;

export function boundedTimeoutMs(value: number | undefined): number {
  if (value === undefined || !Number.isFinite(value)) return 12_000;
  return Math.min(MAX_TIMEOUT_MS, Math.max(MIN_TIMEOUT_MS, Math.trunc(value)));
}

export function boundedRetries(value: number | undefined, method: string, hasIdempotencyKey: boolean): number {
  const safeMethod = ['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase());
  const max = safeMethod || hasIdempotencyKey ? MAX_RETRIES : 0;
  const requested = value === undefined ? 2 : value;
  if (!Number.isFinite(requested)) return 0;
  return Math.max(0, Math.min(max, Math.trunc(requested)));
}

export function retryableHttpStatus(status: number): boolean {
  return status === 408 || status === 429 || status === 502 || status === 503 || status === 504 ||
    (status >= 500 && status < 600);
}

export function retryDelayMs(attempt: number): number {
  const power = Number.isFinite(attempt) ? Math.max(0, Math.min(5, Math.trunc(attempt))) : 0;
  return Math.min(8_000, 400 * (2 ** power));
}

/** Large game workspaces can opt in to more response data without losing a cap. */
export function boundedResponseChars(value: number | undefined): number {
  const fallback = 8 * 1024 * 1024;
  if (value === undefined || !Number.isFinite(value)) return fallback;
  return Math.min(64 * 1024 * 1024, Math.max(1024, Math.trunc(value)));
}
