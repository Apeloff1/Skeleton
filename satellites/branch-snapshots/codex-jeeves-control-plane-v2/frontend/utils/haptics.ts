/**
 * haptics — single, defensive haptic helper with persistent intensity.
 *
 *   • Three intensity levels persisted via AsyncStorage:
 *       'off'    — all haptic calls become no-ops
 *       'light'  — only `tap` and `pulse` fire (selection-level)
 *       'full'   — every call fires its native impact/notification feedback
 *   • Read once at module init, then mutated via `setHapticsLevel(level)`.
 *   • Backward-compat: `setHapticsMuted(true)` maps to level='off'.
 *   • Platform-aware: silently no-ops on web. Wrapped in try/catch.
 */
import { Platform, AccessibilityInfo } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

export type HapticsLevel = 'off' | 'light' | 'full';
const STORAGE_KEY = '@codedock/haptics:level';

let _level: HapticsLevel = 'full';
/** True when the OS reports Reduce-Motion (a.k.a. "Prefer Reduced Motion"
 *  on iOS). We auto-mute *all* haptics whenever this flag is on so users
 *  with vestibular/sensory sensitivity get no surprise vibrations. */
let _reduceMotion = false;

// Hydrate the user choice and the accessibility flag in parallel.
(async () => {
  try {
    const v = await AsyncStorage.getItem(STORAGE_KEY);
    if (v === 'off' || v === 'light' || v === 'full') _level = v;
  } catch { /* swallow */ }
})();

if (Platform.OS !== 'web' && AccessibilityInfo?.isReduceMotionEnabled) {
  AccessibilityInfo.isReduceMotionEnabled()
    .then((flag) => { _reduceMotion = !!flag; })
    .catch(() => {});
  try {
    AccessibilityInfo.addEventListener?.('reduceMotionChanged', (flag: boolean) => {
      _reduceMotion = !!flag;
    });
  } catch { /* swallow */ }
}

export function getHapticsLevel(): HapticsLevel { return _level; }
export function isReduceMotionOn(): boolean { return _reduceMotion; }

/** Effective level after Reduce-Motion override. */
function effectiveLevel(): HapticsLevel {
  if (_reduceMotion) return 'off';
  return _level;
}

export async function setHapticsLevel(level: HapticsLevel): Promise<void> {
  _level = level;
  try { await AsyncStorage.setItem(STORAGE_KEY, level); } catch { /* swallow */ }
}

/** Back-compat shim: `setHapticsMuted(true)` ↔ level='off'. */
export function setHapticsMuted(muted: boolean): void {
  setHapticsLevel(muted ? 'off' : 'full');
}
export function isHapticsMuted(): boolean { return effectiveLevel() === 'off'; }

function _haptics(): any | null {
  if (Platform.OS === 'web') return null;
  try { return require('expo-haptics'); } catch { return null; }
}

function _safe(fn: () => any): void {
  try { fn(); } catch { /* swallow */ }
}

/** Light tap — selections, toggles, card press. Fires on light + full. */
export function tap(): void {
  const lvl = effectiveLevel();
  if (lvl === 'off') return;
  const h = _haptics();
  if (!h) return;
  _safe(() => h.selectionAsync && h.selectionAsync());
}

/** Medium impact — primary tap on FABs, accept-button, etc. Only on full. */
export function impact(): void {
  const lvl = effectiveLevel();
  if (lvl !== 'full') { if (lvl === 'light') return tap(); return; }
  const h = _haptics();
  if (!h) return;
  _safe(() => h.impactAsync && h.impactAsync(h.ImpactFeedbackStyle?.Medium ?? 'medium'));
}

/** Crisp confirmation — successful save, add, pin. Only on full. */
export function success(): void {
  const lvl = effectiveLevel();
  if (lvl !== 'full') { if (lvl === 'light') return tap(); return; }
  const h = _haptics();
  if (!h) return;
  _safe(() => h.notificationAsync && h.notificationAsync(h.NotificationFeedbackType?.Success ?? 'success'));
}

/** Warning. Only on full; light maps to a softer tap. */
export function warn(): void {
  const lvl = effectiveLevel();
  if (lvl !== 'full') { if (lvl === 'light') return tap(); return; }
  const h = _haptics();
  if (!h) return;
  _safe(() => h.notificationAsync && h.notificationAsync(h.NotificationFeedbackType?.Warning ?? 'warning'));
}

/** Error — delete confirm, validation fail. Only on full. */
export function error(): void {
  const lvl = effectiveLevel();
  if (lvl !== 'full') { if (lvl === 'light') return tap(); return; }
  const h = _haptics();
  if (!h) return;
  _safe(() => h.notificationAsync && h.notificationAsync(h.NotificationFeedbackType?.Error ?? 'error'));
}

/** Soft repeated heartbeat. Fires on light + full. */
export function pulse(times = 2, gapMs = 90): void {
  const lvl = effectiveLevel();
  if (lvl === 'off') return;
  const h = _haptics();
  if (!h) return;
  for (let i = 0; i < times; i++) {
    setTimeout(() => _safe(() => h.selectionAsync && h.selectionAsync()), i * gapMs);
  }
}

export default {
  tap, impact, success, warn, error, pulse,
  setHapticsLevel, getHapticsLevel, setHapticsMuted, isHapticsMuted, isReduceMotionOn,
};
