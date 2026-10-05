/**
 * featureFlags — runtime feature toggle registry.
 *
 *   • Backed by AsyncStorage so toggles survive app restarts.
 *   • Defaults declared once in code, override per-device via
 *     /settings/feature-flags or programmatically.
 *   • Read with `useFeatureFlag('foo')` (React hook, reactive)
 *     or `getFeatureFlag('foo')` (synchronous, last-known mirror).
 *   • Write with `setFeatureFlag('foo', true)`.
 *
 *   Common uses:
 *     • Hide a half-built screen behind a flag in production.
 *     • A/B-test a layout without redeploying.
 *     • Disable a heavy feature on low-end devices via thermal monitor.
 */
import { useEffect, useState } from 'react';
import { safeGetItem, safeSetItem, safeRemoveItem } from './safeStorage';

export type FlagCategory =
  | 'Experimental'
  | 'Telemetry'
  | 'Safety'
  | 'Developer';

export interface FlagSpec {
  key:      string;
  default:  boolean;
  label:    string;
  desc?:    string;
  /** When true, the flag is exposed in the settings UI. */
  visible?: boolean;
  /** Grouping in the settings UI. Defaults to 'Experimental'. */
  category?: FlagCategory;
  /** When set, toggling this flag emits a hint about a recommended app reload. */
  requiresReload?: boolean;
}

export const FEATURE_FLAGS: ReadonlyArray<FlagSpec> = [
  // ── Experimental ────────────────────────────────────────────────────
  { key: 'experimental_voice',       default: false, label: 'Voice (experimental)',     desc: 'Jeeves voice mode — preview',                  visible: true, category: 'Experimental' },
  { key: 'experimental_collab',      default: true,  label: 'Live collaboration',       desc: 'Realtime multi-user coding (Collab + Hub)',    visible: true, category: 'Experimental' },
  { key: 'jeeves_audio_test',        default: false, label: 'Jeeves audio test',        desc: 'Show Jeeves audio diagnostics tile',           visible: true, category: 'Experimental' },

  // ── Telemetry ───────────────────────────────────────────────────────
  { key: 'auto_render_trace',        default: true,  label: 'Auto render trace',        desc: 'Log slow screens (>300ms) to telemetry',       visible: true, category: 'Telemetry' },
  { key: 'modal_telemetry_batch',    default: true,  label: 'Modal telemetry batch',    desc: 'Batch modal open/close + action events',       visible: true, category: 'Telemetry' },

  // ── Safety ──────────────────────────────────────────────────────────
  { key: 'safe_mode_auto_route',     default: true,  label: 'Auto safe-mode',           desc: 'After 2 crashes, route to /safe-mode',         visible: true, category: 'Safety' },
  { key: 'apk_self_heal_toolchain',  default: true,  label: 'APK toolchain self-heal',  desc: 'Auto-reinstall Android SDK on missing tools',  visible: true, category: 'Safety', requiresReload: false },

  // ── Developer ───────────────────────────────────────────────────────
  { key: 'show_route_audit',         default: true,  label: 'Show route audit',         desc: 'Show /audit-routes card in Tools',             visible: true, category: 'Developer' },
];

const STORAGE_PREFIX = '@feature/';

// In-memory mirror so synchronous reads work.
const _mirror = new Map<string, boolean>();
const _listeners = new Map<string, Set<(v: boolean) => void>>();

function _broadcast(key: string, value: boolean) {
  const set = _listeners.get(key);
  if (!set) return;
  for (const l of set) { try { l(value); } catch { /* swallow */ } }
}

/** Initialise mirror from AsyncStorage (best-effort). Call once at boot. */
export async function loadFeatureFlags(): Promise<void> {
  for (const f of FEATURE_FLAGS) {
    try {
      const raw = await safeGetItem(STORAGE_PREFIX + f.key, null, 300);
      _mirror.set(f.key, raw === null ? f.default : raw === '1');
    } catch {
      _mirror.set(f.key, f.default);
    }
  }
}

export function getFeatureFlag(key: string): boolean {
  if (_mirror.has(key)) return _mirror.get(key)!;
  const spec = FEATURE_FLAGS.find(f => f.key === key);
  return spec?.default ?? false;
}

export async function setFeatureFlag(key: string, value: boolean): Promise<void> {
  _mirror.set(key, value);
  try { await safeSetItem(STORAGE_PREFIX + key, value ? '1' : '0', 300); } catch { /* swallow */ }
  _broadcast(key, value);
}

export function useFeatureFlag(key: string): boolean {
  const [v, setV] = useState<boolean>(() => getFeatureFlag(key));
  useEffect(() => {
    const set = _listeners.get(key) ?? new Set();
    _listeners.set(key, set);
    set.add(setV);
    // Re-sync once on mount in case loadFeatureFlags resolved late.
    setV(getFeatureFlag(key));
    return () => { set.delete(setV); };
  }, [key]);
  return v;
}

/** Snapshot of every flag's current value (for the settings UI). */
export function getAllFlags(): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const f of FEATURE_FLAGS) out[f.key] = getFeatureFlag(f.key);
  return out;
}

/** Returns the keys of flags whose current value differs from their default. */
export function getModifiedFlagKeys(): string[] {
  const out: string[] = [];
  for (const f of FEATURE_FLAGS) {
    if (getFeatureFlag(f.key) !== f.default) out.push(f.key);
  }
  return out;
}

/** Reset every flag to its declared default (also clears AsyncStorage entry). */
export async function resetAllFlags(): Promise<void> {
  for (const f of FEATURE_FLAGS) {
    _mirror.set(f.key, f.default);
    try { await safeRemoveItem(STORAGE_PREFIX + f.key, 300); } catch { /* swallow */ }
    _broadcast(f.key, f.default);
  }
}

/** Reset a single flag back to its declared default. */
export async function resetFeatureFlag(key: string): Promise<void> {
  const spec = FEATURE_FLAGS.find(f => f.key === key);
  if (!spec) return;
  _mirror.set(key, spec.default);
  try { await safeRemoveItem(STORAGE_PREFIX + key, 300); } catch { /* swallow */ }
  _broadcast(key, spec.default);
}
