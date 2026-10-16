/**
 * Launcher recovery receipt. Persisted fallback attempts expire based on the
 * failure itself, NOT the timestamp of an unrelated healthy boot cache.
 * Old numeric receipts are accepted for backward compatibility.
 *
 * This is a pure policy module so a recovery loop can be tested without
 * importing React, a native storage adapter or an application router.
 */
export const MAX_LAUNCH_LAYER = 3;
export const LAUNCH_ATTEMPT_TTL_MS = 60 * 60 * 1000;

export function clampLaunchLayer(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(MAX_LAUNCH_LAYER, Math.trunc(value)));
}

export function readLaunchAttempt(raw: string | null, now: number = Date.now()): number {
  if (!raw) return 0;
  try {
    const receipt: unknown = JSON.parse(raw);
    if (typeof receipt === 'number') return clampLaunchLayer(receipt);
    if (!receipt || typeof receipt !== 'object') return 0;
    const { layer, at } = receipt as { layer?: unknown; at?: unknown };
    if (typeof at !== 'number' || !Number.isFinite(at) || at > now ||
        now - at > LAUNCH_ATTEMPT_TTL_MS) return 0;
    return clampLaunchLayer(layer);
  } catch {
    return 0;
  }
}

export function writeLaunchAttempt(layer: number, now: number = Date.now()): string {
  const normalized = clampLaunchLayer(layer);
  // Keep the legacy clear-state encoding readable by previous installations.
  return normalized === 0 ? '0' : JSON.stringify({ layer: normalized, at: now });
}

export function shouldAcceptLocalBoot(phase0Done: boolean, criticalOk: boolean): boolean {
  return phase0Done && criticalOk;
}
