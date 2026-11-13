/**
 * Explicit native-storage retention admission.
 *
 * Prefix ownership is not evidence that data is regenerable. Broad project,
 * settings, model, boot and feature-flag namespaces must never be pruned by
 * a background cache cleaner merely because their values are old.
 *
 * This is intentionally an allowlist: adding a cache family requires an
 * explicit design/ownership decision and its own regression coverage.
 */
export const PRUNABLE_EXACT_KEYS = new Set<string>([
  '@boot/last_ok:v1', // advisory warm-boot score; never readiness authority
]);

export const PRUNABLE_CACHE_PREFIXES = Object.freeze([
  '@telemetry/cache/', // disposable derived telemetry cache rows only
]);

export function isPrunableStorageKey(key: string): boolean {
  return PRUNABLE_EXACT_KEYS.has(key) ||
    PRUNABLE_CACHE_PREFIXES.some(prefix => key.startsWith(prefix) && key.length > prefix.length);
}
