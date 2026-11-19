/**
 * safeError — redact exception text before it reaches UI or telemetry.
 *
 * Production screens show a friendly recovery path, not stacks. Crash
 * reports still keep a bounded, secret-stripped diagnostic for admins.
 */

const SECRET_ASSIGNMENT_RE =
  /(?:authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password)\s*[:=]\s*[^\s,;]+/gi;
const BEARER_RE = /bearer\s+[A-Za-z0-9._~+/=-]+/gi;

export function redactSecrets(text: string): string {
  if (!text) return '';
  return text
    .replace(SECRET_ASSIGNMENT_RE, (match) => {
      const separator = match.search(/[:=]/);
      if (separator < 0) return '[REDACTED]';
      return `${match.slice(0, separator + 1)}[REDACTED]`;
    })
    .replace(BEARER_RE, 'Bearer [REDACTED]');
}

export function isDevErrorDetails(): boolean {
  return typeof __DEV__ !== 'undefined' && __DEV__;
}

export function safeErrorMessage(error: unknown): string {
  if (error instanceof Error && error.name) return error.name;
  return 'Error';
}

export function safeErrorDetails(error: unknown): string {
  if (!isDevErrorDetails()) return '';
  if (typeof error === 'string') return redactSecrets(error).slice(0, 2000);
  if (error instanceof Error) {
    return redactSecrets(error.stack || error.message || String(error)).slice(0, 2000);
  }
  return redactSecrets(String(error)).slice(0, 2000);
}

export function crashTelemetryFields(error: unknown): { message: string; stack: string } {
  const err = error instanceof Error ? error : new Error(String(error ?? 'unknown'));
  return {
    message: redactSecrets((err.message || err.name || 'Error').slice(0, 500)),
    stack: redactSecrets((err.stack || err.message || '').slice(0, 2000)),
  };
}
