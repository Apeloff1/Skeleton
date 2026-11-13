/**
 * Bounded, recursive and fail-closed telemetry redaction.
 *
 * All logs and offline queue items pass through this boundary before
 * publication. Redaction is idempotent and never retains raw objects.
 * It intentionally does not attempt to identify every possible secret:
 * prevent free-form error stacks and network payloads at call sites too.
 */
const REDACTED = '[REDACTED]';
const MAX_DEPTH = 5;
const MAX_KEYS = 40;
const MAX_ITEMS = 80;
const MAX_STRING = 1024;

const sensitiveKey = /^(?:authorization|proxy[_-]?authorization|cookie|set[_-]?cookie|pass(?:word|wd)?|secret|client[_-]?secret|api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|credential(?:s)?|private[_-]?key|session[_-]?secret)$/i;

// Match header/value assignments without retaining their credential bytes.
const assignment = /\b(authorization|proxy-authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret|secret|password|passwd|private[_-]?key)\s*[:=]\s*(?:(?:bearer|basic)\s+)?[^\s,;]+/gi;
const bearer = /\b(bearer|basic)\s+[A-Za-z0-9~+/_=.-]+/gi;
const urlCredential = /([?&#](?:api_key|access_token|refresh_token|token|password|secret)=)[^&#\s]+/gi;

function safeText(raw: string): string {
  const capped = raw.slice(0, MAX_STRING * 2);
  return capped
    .replace(assignment, (_match, name: string) => `${name}=${REDACTED}`)
    .replace(bearer, (_match, scheme: string) => `${scheme} ${REDACTED}`)
    .replace(urlCredential, (_match, prefix: string) => `${prefix}${REDACTED}`)
    .slice(0, MAX_STRING);
}

export function scrubTelemetry(value: unknown): unknown {
  const seen = new WeakSet<object>();
  const sanitize = (node: unknown, depth: number): unknown => {
    if (depth >= MAX_DEPTH) return '[TRUNCATED]';
    if (typeof node === 'string') return safeText(node);
    if (node === null || typeof node === 'boolean') return node;
    if (typeof node === 'number') return Number.isFinite(node) ? node : null;
    if (typeof node === 'undefined') return null;
    if (typeof node !== 'object') return '[UNSUPPORTED]';
    if (seen.has(node)) return '[CIRCULAR]';
    seen.add(node);
    if (Array.isArray(node)) {
      return node.slice(0, MAX_ITEMS).map(item => sanitize(item, depth + 1));
    }
    // No prototypes or getters: arbitrary host objects (Error, Response,
    // Proxy, class instances) must not be serialized into diagnostics.
    const proto = Object.getPrototypeOf(node);
    if (proto !== Object.prototype && proto !== null) return '[UNSUPPORTED]';
    const output: Record<string, unknown> = Object.create(null);
    for (const key of Object.keys(node).slice(0, MAX_KEYS)) {
      if (key === '__proto__' || key === 'constructor' || key === 'prototype') continue;
      if (sensitiveKey.test(key)) {
        output[key] = REDACTED;
        continue;
      }
      const descriptor = Object.getOwnPropertyDescriptor(node, key);
      if (!descriptor || !('value' in descriptor)) {
        output[key] = '[UNSUPPORTED]';
        continue;
      }
      output[safeText(key)] = sanitize(descriptor.value, depth + 1);
    }
    return output;
  };
  try {
    return sanitize(value, 0);
  } catch {
    // Exotic proxy traps and host objects can throw even during inspection.
    return '[UNSUPPORTED]';
  }
}
