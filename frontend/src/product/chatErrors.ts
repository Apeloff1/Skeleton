import type { ApiResult } from '../utils/apiClient';

export type ChatErrorKind =
  | 'authorization' | 'conflict' | 'unavailable' | 'network'
  | 'timeout' | 'cancelled' | 'validation' | 'protocol' | 'execution';

/** Safe, actionable product failure; request correlation survives each API hop. */
export class ChatClientError extends Error {
  readonly kind: ChatErrorKind;
  readonly code: string;
  readonly status: number;
  readonly requestId: string | null;
  readonly retryable: boolean;

  constructor(message: string, input: {
    kind?: ChatErrorKind; code?: string; status?: number;
    requestId?: string | null; retryable?: boolean;
  } = {}) {
    super(message);
    this.name = 'ChatClientError';
    this.kind = input.kind ?? 'protocol';
    this.code = input.code ?? this.kind;
    this.status = input.status ?? 0;
    this.requestId = input.requestId ?? null;
    this.retryable = input.retryable ?? ['network', 'timeout', 'unavailable'].includes(this.kind);
  }
}

function safeMessage(value: unknown, depth = 0): string | null {
  if (depth > 4) return null;
  if (typeof value === 'string' && value.trim()) return value.slice(0, 1200);
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const object = value as Record<string, unknown>;
    return safeMessage(object.message, depth + 1) ?? safeMessage(object.detail, depth + 1) ?? safeMessage(object.error, depth + 1);
  }
  return null;
}

export function chatApiError(result: ApiResult<unknown>, fallback: string): ChatClientError {
  const payload = result.data && typeof result.data === 'object'
    ? result.data as Record<string, unknown> : null;
  const detail = payload?.detail;
  const structured = detail && typeof detail === 'object' && !Array.isArray(detail)
    ? detail as Record<string, unknown> : payload;
  const transport = safeMessage(result.error);
  const status = result.status;
  const kind: ChatErrorKind = transport === 'aborted' ? 'cancelled'
    : transport === 'timeout' ? 'timeout'
      : status === 401 || status === 403 ? 'authorization'
        : status === 409 ? 'conflict'
          : status === 422 || status === 400 ? 'validation'
            : status === 429 || status >= 500 ? 'unavailable'
              : status === 0 ? 'network' : 'execution';
  // Server faults, transport failures and throttling are not user-safe prose.
  // Preserve the stable code and correlation ID, never an internal traceback.
  const visible = (status >= 500 || status === 429 || status === 0)
    ? fallback : (safeMessage(detail) ?? transport ?? fallback);
  const rawCode = structured?.code;
  const code = typeof rawCode === 'string' && /^[a-z][a-z0-9_.-]{0,80}$/i.test(rawCode)
    ? rawCode : kind;
  const requestId = typeof result.rid === 'string' && result.rid.length <= 128
    ? result.rid : null;
  return new ChatClientError(visible, { kind, status, requestId, code });
}

export function asChatError(error: unknown, fallback = 'The conversation could not be updated.'): ChatClientError {
  if (error instanceof ChatClientError) return error;
  if (error instanceof Error && error.name === 'ConversationProjectionError') {
    return new ChatClientError(error.message, { kind: 'protocol', code: (error as Error & { code?: string }).code ?? 'invalid_projection' });
  }
  if (error instanceof Error && (error.name === 'AbortError' || error.message === 'aborted')) {
    return new ChatClientError('Request detached.', { kind: 'cancelled', retryable: false });
  }
  // Unknown thrown errors can contain connection strings or backend internals.
  return new ChatClientError(fallback, { kind: 'network', retryable: true });
}

export function chatAbortError(): ChatClientError {
  return new ChatClientError('Request detached.', { kind: 'cancelled', retryable: false });
}
