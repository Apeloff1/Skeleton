/**
 * Minimal, private-by-default telemetry envelope.
 *
 * Telemetry is an observability channel, not an error-reporting dump. Never
 * collect stack traces, exception messages, arbitrary strings, network URLs,
 * prompts, user identifiers, auth headers or full objects. All caller-provided
 * fields are untrusted, including values persisted into offline AsyncStorage.
 *
 * The backend independently enforces the same coarse policy: clients may
 * bypass this module, downgrade, or submit forged events.
 */

export type SafeTelemetryValue = number | boolean | string;
export type SafeTelemetryDetail = Record<string, SafeTelemetryValue>;

const ALLOWED_EVENT_NAMES = new Set([
  'open', 'close', 'nav', 'warn', 'error', 'fatal',
  'crash', 'metric', 'custom', 'other',
]);

const SAFE_STRING_VALUE_FIELDS = new Set([
  'status', 'state', 'phase', 'kind', 'mode', 'unit', 'result',
]);

const SAFE_ENUMS = new Set([
  'ok', 'success', 'failed', 'failure', 'error', 'warning',
  'pending', 'queued', 'running', 'started', 'stopped',
  'completed', 'cancelled', 'canceled', 'timeout', 'retrying',
  'skipped', 'unknown', 'available', 'unavailable', 'healthy',
  'unhealthy', 'connected', 'disconnected', 'offline', 'online',
  'enabled', 'disabled', 'valid', 'invalid', 'open', 'closed',
  'visible', 'hidden', 'primary', 'secondary', 'local', 'remote',
  'web', 'native', 'android', 'ios', 'desktop', 'macos',
  'windows', 'linux', 'dev', 'test', 'prod', 'development',
  'production', 'zip', 'apk', 'pdf', 'json', 'text', 'image',
  'audio', 'video', 'python', 'javascript', 'typescript',
  'seconds', 'milliseconds', 'bytes', 'count', 'percent',
]);

const SAFE_ERROR_NAMES = new Set([
  'Error', 'TypeError', 'ReferenceError', 'RangeError', 'SyntaxError',
  'URIError', 'EvalError', 'AggregateError', 'NetworkError',
  'AbortError', 'TimeoutError',
]);

// A payload key that resembles PII, credentials, arbitrary request content,
// error text or a filesystem/network locator cannot enter the telemetry queue.
const DENIED_KEY = /token|secret|pass|auth|cookie|credential|session|identity|user|name|email|phone|address|location|url|uri|path|stack|message|prompt|code|query|body|payload|header|account|card|pin|key|client|response|request|text|value|content|ip/i;

export function safeTelemetryLabel(value: unknown, maxLength = 80): string {
  if (typeof value !== 'string' || value.length > maxLength ||
      !/^[A-Za-z][A-Za-z0-9_.:/-]*$/.test(value)) return 'unknown';
  return value;
}

export function safeTelemetryEvent(value: unknown): string {
  if (typeof value !== 'string') return 'other';
  if (ALLOWED_EVENT_NAMES.has(value)) return value;
  if (/^action:[A-Za-z][A-Za-z0-9_-]{0,47}$/.test(value)) return value;
  return 'other';
}

export function safeTelemetryErrorType(value: unknown): string {
  if (value && typeof value === 'object') {
    // Do not inspect a thrown object's prototype, .message, .stack or custom
    // getters. Error names are only classified via an own data descriptor.
    try {
      const descriptor = Object.getOwnPropertyDescriptor(value, 'name');
      if (descriptor && 'value' in descriptor && typeof descriptor.value === 'string' &&
          SAFE_ERROR_NAMES.has(descriptor.value)) return descriptor.value;
    } catch {
      // An untrusted Proxy may throw while being inspected.
    }
  }
  return 'Error';
}

export function sanitizeTelemetryDetail(value: unknown): SafeTelemetryDetail | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  let descriptors: PropertyDescriptorMap;
  try {
    // Descriptors avoid running potentially sensitive or side-effectful getters.
    descriptors = Object.getOwnPropertyDescriptors(value);
  } catch {
    return undefined;
  }
  const safe: SafeTelemetryDetail = Object.create(null);
  for (const key of Object.keys(descriptors).slice(0, 24)) {
    if (key.length > 40 || !/^[A-Za-z][A-Za-z0-9_]*$/.test(key) ||
        DENIED_KEY.test(key)) continue;
    const descriptor = descriptors[key];
    if (!descriptor || !('value' in descriptor)) continue;
    const entry: unknown = descriptor.value;
    if (typeof entry === 'boolean') {
      safe[key] = entry;
    } else if (typeof entry === 'number' && Number.isFinite(entry) &&
               Math.abs(entry) <= 1_000_000_000) {
      safe[key] = entry;
    } else if (typeof entry === 'string' && SAFE_STRING_VALUE_FIELDS.has(key) &&
               SAFE_ENUMS.has(entry.toLowerCase())) {
      safe[key] = entry.toLowerCase();
    } else if (key === 'error_type' && typeof entry === 'string' &&
               SAFE_ERROR_NAMES.has(entry)) {
      safe[key] = entry;
    }
  }
  return Object.keys(safe).length ? safe : undefined;
}
