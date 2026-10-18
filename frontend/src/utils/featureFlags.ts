/**
 * featureFlags — runtime feature toggle registry.
 *
 *   • Backed by AsyncStorage so toggles survive app restarts.
 *   • Defaults declared once in code, override per-device via
 *     /settings/feature-flags or programmatically.
 *   • Read with `useFeatureFlag('foo')` (React hook, reactive)
 *     or `getFeatureFlag('foo')` (synchronous, last-known mirror).
 *   • Write with `setFeatureFlag('foo', true)`.
 */
import { useEffect, useState } from 'react';
import { safeGetItem, safeSetItem, safeRemoveItem } from './safeStorage';

export type FlagCategory =
  | 'Experimental'
  | 'Telemetry'
  | 'Safety'
  | 'Developer';

export interface FlagSpec {
  key: string;
  default: boolean;
  label: string;
  desc?: string;
  visible?: boolean;
  category?: FlagCategory;
  requiresReload?: boolean;
}

export const FEATURE_FLAGS: ReadonlyArray<FlagSpec> = [
  { key: 'experimental_voice', default: false, label: 'Voice (experimental)', desc: 'Jeeves voice mode — preview', visible: true, category: 'Experimental' },
  { key: 'experimental_collab', default: true, label: 'Live collaboration', desc: 'Realtime multi-user coding (Collab + Hub)', visible: true, category: 'Experimental' },
  { key: 'jeeves_audio_test', default: false, label: 'Jeeves audio test', desc: 'Show Jeeves audio diagnostics tile', visible: true, category: 'Experimental' },
  { key: 'auto_render_trace', default: true, label: 'Auto render trace', desc: 'Log slow screens (>300ms) to telemetry', visible: true, category: 'Telemetry' },
  { key: 'modal_telemetry_batch', default: true, label: 'Modal telemetry batch', desc: 'Batch modal open/close + action events', visible: true, category: 'Telemetry' },
  { key: 'safe_mode_auto_route', default: true, label: 'Auto safe-mode', desc: 'After 2 crashes, route to /safe-mode', visible: true, category: 'Safety' },
  { key: 'apk_self_heal_toolchain', default: true, label: 'APK toolchain self-heal', desc: 'Auto-reinstall Android SDK on missing tools', visible: true, category: 'Safety', requiresReload: false },
  { key: 'show_route_audit', default: true, label: 'Show route audit', desc: 'Show /audit-routes card in Tools', visible: true, category: 'Developer' },
];

const STORAGE_PREFIX = '@feature/';
const mirror = new Map<string, boolean>();
const listeners = new Map<string, Set<(value: boolean) => void>>();

function broadcast(key: string, value: boolean) {
  const subscribers = listeners.get(key);
  if (!subscribers) return;
  for (const listener of subscribers) {
    try { listener(value); } catch {}
  }
}

/**
 * Hydrate all local flags concurrently.
 *
 * The old implementation performed one bounded storage read after another,
 * stretching eight 300ms budgets across the startup window. It also updated
 * the mirror silently, so a hook that subscribed before hydration completed
 * could remain stuck on its default value. We now resolve reads in parallel
 * and broadcast only values that actually changed.
 */
export async function loadFeatureFlags(): Promise<void> {
  const loaded = await Promise.all(FEATURE_FLAGS.map(async spec => {
    let value = spec.default;
    try {
      const raw = await safeGetItem(STORAGE_PREFIX + spec.key, null, 300);
      value = raw === null ? spec.default : raw === '1';
    } catch {}
    return [spec.key, value] as const;
  }));

  for (const [key, value] of loaded) {
    const previous = mirror.get(key);
    mirror.set(key, value);
    if (previous !== value) broadcast(key, value);
  }
}

export function getFeatureFlag(key: string): boolean {
  if (mirror.has(key)) return mirror.get(key)!;
  const spec = FEATURE_FLAGS.find(flag => flag.key === key);
  return spec?.default ?? false;
}

export async function setFeatureFlag(key: string, value: boolean): Promise<void> {
  mirror.set(key, value);
  try { await safeSetItem(STORAGE_PREFIX + key, value ? '1' : '0', 300); } catch {}
  broadcast(key, value);
}

export function useFeatureFlag(key: string): boolean {
  const [value, setValue] = useState<boolean>(() => getFeatureFlag(key));
  useEffect(() => {
    const subscribers = listeners.get(key) ?? new Set<(value: boolean) => void>();
    listeners.set(key, subscribers);
    subscribers.add(setValue);
    setValue(getFeatureFlag(key));
    return () => { subscribers.delete(setValue); };
  }, [key]);
  return value;
}

export function getAllFlags(): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const flag of FEATURE_FLAGS) out[flag.key] = getFeatureFlag(flag.key);
  return out;
}

export function getModifiedFlagKeys(): string[] {
  const out: string[] = [];
  for (const flag of FEATURE_FLAGS) {
    if (getFeatureFlag(flag.key) !== flag.default) out.push(flag.key);
  }
  return out;
}

export async function resetAllFlags(): Promise<void> {
  for (const flag of FEATURE_FLAGS) {
    mirror.set(flag.key, flag.default);
    try { await safeRemoveItem(STORAGE_PREFIX + flag.key, 300); } catch {}
    broadcast(flag.key, flag.default);
  }
}

export async function resetFeatureFlag(key: string): Promise<void> {
  const spec = FEATURE_FLAGS.find(flag => flag.key === key);
  if (!spec) return;
  mirror.set(key, spec.default);
  try { await safeRemoveItem(STORAGE_PREFIX + key, 300); } catch {}
  broadcast(key, spec.default);
}
