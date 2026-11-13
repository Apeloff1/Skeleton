/**
 * safeJson — defensive JSON helpers.
 *
 *   • safeJsonParse(text, fallback)  — never throws; returns fallback
 *     on parse failure with optional `onError(err)` callback.
 *   • safeJsonStringify(value, fallback) — handles cyclic references
 *     via a WeakSet, returns fallback on TypeError.
 *
 * Why this exists:
 *   React Native screens routinely deserialize API responses, cached
 *   AsyncStorage blobs, and clipboard contents. A single malformed
 *   payload throws `SyntaxError` synchronously and can unmount an
 *   entire screen. safeJsonParse keeps the screen alive with a sane
 *   default while still recording the failure to telemetry.
 */
import { recordEvent } from './modalLogger';

export function safeJsonParse<T = any>(text: string | null | undefined, fallback: T, onError?: (e: any) => void): T {
  if (text == null) return fallback;
  if (typeof text !== 'string') return fallback;
  if (text.length === 0) return fallback;
  // ★ Guard against pathological payloads (e.g. corrupted clipboards or
  // log dumps) that would lock up the parser for seconds.
  if (text.length > 10 * 1024 * 1024) {
    try { recordEvent('safeJsonParse', 'oversize_skip', 'warn', { bytes: text.length }); } catch { /* swallow */ }
    return fallback;
  }
  try {
    return JSON.parse(text) as T;
  } catch (e) {
    try {
      onError?.(e);
      recordEvent('safeJsonParse', 'parse_error', 'warn', { sample: text.slice(0, 80), err: String((e as any)?.message || e) });
    } catch { /* swallow */ }
    return fallback;
  }
}

export function safeJsonStringify(value: any, fallback = '{}'): string {
  const seen = new WeakSet<object>();
  try {
    return JSON.stringify(value, (_key, v) => {
      if (typeof v === 'object' && v !== null) {
        if (seen.has(v)) return '[Cyclic]';
        seen.add(v);
      }
      // Functions / undefined become null so the structure survives.
      if (typeof v === 'function') return '[Function]';
      return v;
    });
  } catch (e) {
    try {
      recordEvent('safeJsonStringify', 'stringify_error', 'warn', { err: String((e as any)?.message || e) });
    } catch { /* swallow */ }
    return fallback;
  }
}
