/**
 * Privacy boundary for client telemetry.
 *
 * Only bounded and redacted JSON-safe data leaves the client or reaches
 * AsyncStorage. This is intentionally independent of navigation/session state.
 * A caught Error's message and stack are never telemetry-safe by default.
 */

const MAX_FIELD = 512;
const MAX_KEYS = 32;
const MAX_ITEMS = 32;
const MAX_DEPTH = 4;
const SECRET_KEY = /(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|session[_-]?key|authorization|credential|cookie|jwt|bearer|private[_-]?key)/i;
const UNSAFE_KEY = new Set(['__proto__', 'constructor', 'prototype']);

export function redactTelemetryText(input: string, max = MAX_FIELD): string {
  const bounded = input.slice(0, Math.max(0, Math.min(max, MAX_FIELD)));
  // Credential forms may appear in HTTP errors, database messages and URLs.
  return bounded
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer [REDACTED]')
    .replace(/\b(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|client[_-]?secret|cookie)\b\s*[:=]\s*[^\s&;,]+/gi, '[REDACTED]')
    .replace(/([?&](?:token|api[_-]?key|secret|password|code|session|access[_-]?token)=)[^&#\s]+/gi, '$1[REDACTED]');
}

export function sanitizeTelemetryDetail(
  value: unknown,
  depth = 0,
  visited = new WeakSet<object>(),
): unknown {
  if (depth >= MAX_DEPTH) return '[TRUNCATED]';
  if (value == null) return null;
  if (typeof value === 'string') return redactTelemetryText(value);
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'object') return '[UNSUPPORTED]';
  if (visited.has(value)) return '[CIRCULAR]';
  visited.add(value);
  try {
    if (Array.isArray(value)) {
      return value.slice(0, MAX_ITEMS).map(item =>
        sanitizeTelemetryDetail(item, depth + 1, visited),
      );
    }
    // Never execute class instance custom serialization (Error.toJSON etc.).
    if (Object.getPrototypeOf(value) !== Object.prototype &&
        Object.getPrototypeOf(value) !== null) {
      return '[UNSUPPORTED]';
    }
    const safe: Record<string, unknown> = Object.create(null);
    for (const key of Object.keys(value).slice(0, MAX_KEYS)) {
      if (UNSAFE_KEY.has(key)) continue;
      const normalized = redactTelemetryText(key, 64);
      if (SECRET_KEY.test(key)) {
        safe[normalized] = '[REDACTED]';
        continue;
      }
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (!descriptor || !('value' in descriptor)) {
        safe[normalized] = '[ACCESSOR_REDACTED]';
        continue;
      }
      safe[normalized] = sanitizeTelemetryDetail(
        descriptor.value, depth + 1, visited,
      );
    }
    return safe;
  } finally {
    visited.delete(value);
  }
}

export interface SanitizedTelemetry {
  modal_id: string;
  session_id: string;
  event: string;
  severity: 'info' | 'warn' | 'error' | 'fatal';
  ts_client?: number;
  duration_ms?: number;
  detail?: unknown;
}

export function sanitizeTelemetryEvent(value: unknown): SanitizedTelemetry | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const item = value as Record<string, unknown>;
  if (typeof item.modal_id !== 'string' ||
      typeof item.event !== 'string' ||
      typeof item.session_id !== 'string') return null;
  const validSeverities = ['info', 'warn', 'error', 'fatal'];
  const severity = validSeverities.includes(String(item.severity))
    ? item.severity as SanitizedTelemetry['severity'] : 'info';
  const validNumber = (num: unknown) =>
    typeof num === 'number' && Number.isFinite(num) ? num : undefined;
  return {
    modal_id: redactTelemetryText(item.modal_id, 80),
    session_id: redactTelemetryText(item.session_id, 80),
    event: redactTelemetryText(item.event, 64),
    severity,
    ts_client: validNumber(item.ts_client),
    duration_ms: validNumber(item.duration_ms),
    detail: sanitizeTelemetryDetail(item.detail),
  };
}
