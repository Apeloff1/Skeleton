/**
 * Operator-facing error normalisation.
 *
 * The engine answers failures in three shapes:
 *   • SkeletonError handler  → `{ error: { type, code, message, context } }`
 *     (e.g. CockpitError `CTX.COCKPIT` 400 with `context.known`, AuthError 401);
 *   • FastAPI HTTPException  → `{ detail: string | { error, reason, … } }`
 *     (charter_denied 403, "seal unavailable" 503, bad playtest mode 422);
 *   • transport failures from src/utils/apiClient (`timeout`, `circuit_open`,
 *     `network_error`, `aborted`) with status 0.
 *
 * `toOperatorError` folds all of them into one discriminated record with a
 * concrete next step, so screens never print `[object Object]`.
 */

export type OperatorErrorKind =
  | 'seal_missing'
  | 'seal_invalid'
  | 'seal_unavailable'
  | 'charter_denied'
  | 'ops_unauthorized'
  | 'cockpit'
  | 'validation'
  | 'not_ready'
  | 'not_found'
  | 'timeout'
  | 'offline'
  | 'circuit_open'
  | 'aborted'
  | 'server';

export interface OperatorError {
  kind: OperatorErrorKind;
  status: number;
  message: string;
  hint: string;
  code?: string;
  context?: Record<string, unknown>;
  requestId?: string | null;
}

const HINTS: Record<OperatorErrorKind, string> = {
  seal_missing: 'This action is sealed. Paste an x-gf-seal minted for this engine in Connection.',
  seal_invalid: 'The engine rejected the seal (expired, wrong key or malformed). Mint a fresh one.',
  seal_unavailable: 'The engine has no GF_SEAL_SECRET / keyring configured, so sealed routes are closed.',
  charter_denied: 'Governance denied this action for the current actor weight. Raise x-gf-actor-weight or amend the charter.',
  ops_unauthorized: 'The ops token does not match OPS_TOKEN on the application backend.',
  cockpit: 'The cockpit rejected the command. Check the verb grammar below.',
  validation: 'The request was rejected by input validation.',
  not_ready: 'The engine subsystem is not wired yet (boot incomplete). Retry after genesis finishes.',
  not_found: 'The endpoint or record does not exist on this backend build.',
  timeout: 'The request timed out. Forge runs with playtest can take a while; retry or lower the playtest mode.',
  offline: 'The backend is unreachable. Check the engine URL and that the service is running.',
  circuit_open: 'Too many recent failures; requests are paused briefly to let the backend recover.',
  aborted: 'Request cancelled.',
  server: 'The backend failed while handling the request. See the message for details.',
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function str(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Pull the most specific human message out of any backend error body. */
export function extractMessage(body: unknown): { message: string; code?: string; context?: Record<string, unknown> } {
  if (typeof body === 'string') return { message: body };
  const rec = asRecord(body);
  if (!rec) return { message: '' };
  const envelope = asRecord(rec.error);
  if (envelope) {
    return {
      message: str(envelope.message) || str(envelope.type),
      code: str(envelope.code) || undefined,
      context: asRecord(envelope.context) ?? undefined,
    };
  }
  if (typeof rec.error === 'string') return { message: rec.error };
  const detail = rec.detail;
  if (typeof detail === 'string') return { message: detail };
  const detailRec = asRecord(detail);
  if (detailRec) {
    const reason = str(detailRec.reason);
    const err = str(detailRec.error) || str(detailRec.code);
    const message = str(detailRec.message);
    return {
      message: [err, message || reason].filter(Boolean).join(': ') || str(detailRec),
      code: err || undefined,
      context: detailRec,
    };
  }
  if (Array.isArray(detail)) {
    // pydantic 422: [{ loc, msg, type }]
    const parts = detail
      .map((d) => {
        const item = asRecord(d);
        if (!item) return str(d);
        const loc = Array.isArray(item.loc) ? item.loc.filter((x) => x !== 'body').join('.') : '';
        return loc ? `${loc}: ${str(item.msg)}` : str(item.msg);
      })
      .filter(Boolean);
    return { message: parts.join('; ') };
  }
  return { message: str(rec.message) };
}

export interface TransportFailure {
  status: number;
  error: unknown;
  data: unknown;
  rid?: string | null;
}

/**
 * Normalise an apiClient failure. `sealed` marks routes behind require_seal /
 * require_charter so a 401 is explained as a seal problem rather than login.
 */
export function toOperatorError(failure: TransportFailure, opts: { sealed?: boolean; sealPresent?: boolean; ops?: boolean } = {}): OperatorError {
  const { status } = failure;
  const fromBody = extractMessage(failure.data);
  const transport = typeof failure.error === 'string' ? failure.error : extractMessage(failure.error).message;
  const message = fromBody.message || transport || (status ? `HTTP ${status}` : 'request failed');
  const base = { status, message, code: fromBody.code, context: fromBody.context, requestId: failure.rid ?? null };
  const lower = message.toLowerCase();

  let kind: OperatorErrorKind;
  if (status === 0) {
    if (transport === 'timeout') kind = 'timeout';
    else if (transport === 'circuit_open') kind = 'circuit_open';
    else if (transport === 'aborted') kind = 'aborted';
    else kind = 'offline';
  } else if (status === 401) {
    kind = opts.sealed ? (opts.sealPresent ? 'seal_invalid' : 'seal_missing') : 'seal_invalid';
  } else if (status === 403) {
    if (opts.ops) kind = 'ops_unauthorized';
    else if (fromBody.code === 'charter_denied' || lower.includes('charter')) kind = 'charter_denied';
    else kind = opts.sealed ? 'seal_invalid' : 'ops_unauthorized';
  } else if (status === 503 && lower.includes('seal')) {
    kind = 'seal_unavailable';
  } else if (status === 503) {
    kind = 'not_ready';
  } else if (status === 404) {
    kind = 'not_found';
  } else if (status === 400 && fromBody.code === 'CTX.COCKPIT') {
    kind = 'cockpit';
  } else if (status === 400 || status === 422) {
    kind = 'validation';
  } else {
    kind = 'server';
  }
  return { kind, hint: HINTS[kind], ...base };
}

export function operatorErrorFromException(err: unknown): OperatorError {
  const message = err instanceof Error ? err.message : str(err) || 'unexpected error';
  return { kind: 'server', status: 0, message, hint: HINTS.server };
}

/** True when retrying the same request later could succeed. */
export function isTransient(err: OperatorError): boolean {
  return err.kind === 'timeout' || err.kind === 'offline' || err.kind === 'circuit_open' || err.kind === 'not_ready';
}

/** Allowed values the engine listed in a rejection (e.g. unknown archetype → context.known). */
export function knownValues(err: OperatorError | null | undefined): string[] {
  const known = err?.context?.known;
  return Array.isArray(known) ? known.map((k) => String(k)) : [];
}
