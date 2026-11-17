/**
 * bootTracer — persistent boot-progress recorder + crash-loop safe-mode.
 *
 *   import { traceStep, getLastTrace, getCrashCount, markCrash, clearCrashes } from './bootTracer';
 *
 *   traceStep('layout_mounted');     // call at each critical mount point
 *   traceStep('hub_imports_loaded');
 *   traceStep('hub_render_ok');
 *
 * Storage shape (all under @boot/* keys in AsyncStorage):
 *   @boot/trace        — array<{step, ts}>  (last 50 steps, rolling)
 *   @boot/crash_count  — number             (number of consecutive crashes since last clean boot)
 *   @boot/last_clean_boot — ts              (timestamp of last successful full boot)
 *
 * Crash-loop protection:
 *   - bootGuard() reads crash_count on app start. If >= 2, returns 'safe-mode'
 *     so /app/index.tsx can redirect there instead of /hub.
 *   - traceStep('app_ready') resets crash_count to 0.
 *
 * NOTE: All AsyncStorage calls are best-effort. Never throws.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY_TRACE       = '@boot/trace';
const KEY_SESSIONS    = '@boot/sessions';   // ring of previous sessions (crash-durable)
const MAX_SESSIONS    = 6;                   // keep last 6 session traces
const KEY_CRASH_COUNT = '@boot/crash_count';
const KEY_LAST_CLEAN  = '@boot/last_clean_boot';
const MAX_TRACE_LEN   = 150;

/** Process-start epoch so every trace line carries a monotonic +Xms offset. */
const _T0 = Date.now();

export interface TraceStep {
  step: string;
  ts:   number;
}

let _memoryTrace: TraceStep[] = [];  // mirror so synchronous reads work

// ── Live trace pub/sub (drives the on-screen DevLogOverlay) ─────────────
type TraceListener = (t: TraceStep[]) => void;
const _listeners = new Set<TraceListener>();
function _notify(): void {
  const snap = [..._memoryTrace];
  // Defer listener (React setState) out of the current render/commit phase —
  // traceStepSync is sometimes called DURING render (e.g. hub_render_enter),
  // and notifying synchronously would "setState while rendering another
  // component". queueMicrotask schedules it safely after the current frame.
  const run = () => { _listeners.forEach(l => { try { l(snap); } catch {} }); };
  try {
    if (typeof queueMicrotask === 'function') queueMicrotask(run);
    else setTimeout(run, 0);
  } catch { run(); }
}
/** Subscribe to live trace updates. Fires immediately with current trace. */
export function subscribeTrace(cb: TraceListener): () => void {
  _listeners.add(cb);
  try { cb([..._memoryTrace]); } catch {}
  return () => { _listeners.delete(cb); };
}

// ── Universal "any crash → Safe Mode" router ────────────────────────────
let _navTs = 0;
/**
 * Navigate to /safe-mode from ANYWHERE (global error handler, ErrorBoundary,
 * ScreenGuard). Debounced + loop-guarded so we never ping-pong. Records the
 * reason durably first so the Safe-Mode screen shows what triggered it.
 */
export function navToSafeMode(reason: string): void {
  const now = Date.now();
  if (now - _navTs < 1500) return;          // debounce repeated triggers
  _navTs = now;
  traceStepSync(`NAV_SAFE_MODE ${reason}`.slice(0, 120));
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { router, usePathname } = require('expo-router');
    // Best-effort: don't re-navigate if we're already on safe-mode.
    let here = '';
    try { here = (globalThis as any).__lastPathname || ''; } catch {}
    void usePathname; // not callable outside React; rely on __lastPathname
    if (here.includes('safe-mode')) return;
    setTimeout(() => { try { router.replace('/safe-mode'); } catch {} }, 0);
  } catch { /* router unavailable — swallow */ }
}

export async function traceStep(step: string, extra?: Record<string, any>): Promise<void> {
  const label = extra ? `${step} ${JSON.stringify(extra).slice(0, 120)}` : step;
  const row: TraceStep = { step: label, ts: Date.now() };
  _memoryTrace.push(row);
  if (_memoryTrace.length > MAX_TRACE_LEN) _memoryTrace = _memoryTrace.slice(-MAX_TRACE_LEN);
  // Console mirror — shows in Metro / `adb logcat` right up to a native
  // crash, the single most reliable trail for diagnosing device force-close.
  try { console.log(`[BOOTTRACE +${row.ts - _T0}ms] ${label}`); } catch {}
  _notify();
  try {
    await AsyncStorage.setItem(KEY_TRACE, JSON.stringify(_memoryTrace));
  } catch { /* swallow */ }
}

/**
 * Synchronous trace — records to the in-memory mirror + console IMMEDIATELY
 * (no await), then flushes to AsyncStorage fire-and-forget. Use at hot paths
 * (module eval, render entry) where we can't await but still want the line
 * captured before a potential synchronous native crash.
 */
export function traceStepSync(step: string, extra?: Record<string, any>): void {
  const label = extra ? `${step} ${JSON.stringify(extra).slice(0, 120)}` : step;
  const row: TraceStep = { step: label, ts: Date.now() };
  _memoryTrace.push(row);
  if (_memoryTrace.length > MAX_TRACE_LEN) _memoryTrace = _memoryTrace.slice(-MAX_TRACE_LEN);
  try { console.log(`[BOOTTRACE +${row.ts - _T0}ms] ${label}`); } catch {}
  _notify();
  try { AsyncStorage.setItem(KEY_TRACE, JSON.stringify(_memoryTrace)).catch(() => {}); } catch {}
}

let _crashTraceInstalled = false;
/**
 * Install a global trap so any uncaught JS error / unhandled promise
 * rejection is recorded durably BEFORE the runtime tears down. Call once,
 * as early as possible (root layout). Idempotent.
 */
export function installCrashTrace(): void {
  if (_crashTraceInstalled) return;
  _crashTraceInstalled = true;
  try {
    const g: any = globalThis as any;
    // React Native global error handler (ErrorUtils).
    const EU = g.ErrorUtils;
    if (EU?.getGlobalHandler && EU?.setGlobalHandler) {
      const prev = EU.getGlobalHandler();
      EU.setGlobalHandler((err: any, isFatal?: boolean) => {
        traceStepSync(`GLOBAL_ERROR fatal=${!!isFatal} ${String(err?.message || err).slice(0, 140)}`);
        // Any fatal JS error → route to Safe Mode (universal crash funnel).
        if (isFatal) { try { navToSafeMode('global_error'); } catch {} }
        try { prev && prev(err, isFatal); } catch {}
      });
    }
    // Unhandled promise rejections (web + Hermes where supported).
    if (typeof g.addEventListener === 'function') {
      g.addEventListener('unhandledrejection', (ev: any) => {
        traceStepSync(`UNHANDLED_REJECTION ${String(ev?.reason?.message || ev?.reason || ev).slice(0, 140)}`);
      });
    }
    traceStepSync('crash_trace_installed');
  } catch { /* never block boot */ }
}

export async function getLastTrace(): Promise<TraceStep[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY_TRACE);
    if (!raw) return [];
    return JSON.parse(raw) as TraceStep[];
  } catch { return []; }
}

export interface ArchivedSession { at: number; steps: TraceStep[] }

/**
 * "Log the logs" — returns the archived traces of PREVIOUS app sessions
 * (including ones that crashed). These survive crashes AND reboots because
 * rotateSessionsOnce() snapshots the prior @boot/trace into the ring before
 * the new session overwrites it.
 */
export async function getSessionArchive(): Promise<ArchivedSession[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY_SESSIONS);
    if (!raw) return [];
    const arc = JSON.parse(raw);
    return Array.isArray(arc) ? arc : [];
  } catch { return []; }
}

let _rotated = false;
/**
 * Run ONCE per process at the earliest possible point (this module's eval, so
 * the read is queued in AsyncStorage BEFORE any new traceStep write). Moves the
 * previous session's trace into the durable session ring so a crash's final
 * breadcrumbs are never lost when the next launch starts overwriting @boot/trace.
 */
async function rotateSessionsOnce(): Promise<void> {
  if (_rotated) return; _rotated = true;
  try {
    const prevRaw = await AsyncStorage.getItem(KEY_TRACE);
    if (!prevRaw) return;
    const prev = JSON.parse(prevRaw);
    if (!Array.isArray(prev) || prev.length === 0) return;
    let arc: ArchivedSession[] = [];
    try { const a = await AsyncStorage.getItem(KEY_SESSIONS); arc = a ? JSON.parse(a) : []; } catch {}
    if (!Array.isArray(arc)) arc = [];
    arc.unshift({ at: Date.now(), steps: prev.slice(-80) });
    arc = arc.slice(0, MAX_SESSIONS);
    await AsyncStorage.setItem(KEY_SESSIONS, JSON.stringify(arc));
  } catch { /* never block */ }
}
// Kick rotation immediately on module load (queues the read before writes).
rotateSessionsOnce();

export async function getCrashCount(): Promise<number> {
  try {
    const v = await AsyncStorage.getItem(KEY_CRASH_COUNT);
    return v ? parseInt(v, 10) || 0 : 0;
  } catch { return 0; }
}

export async function markCrash(): Promise<number> {
  const n = (await getCrashCount()) + 1;
  try { await AsyncStorage.setItem(KEY_CRASH_COUNT, String(n)); } catch { /* swallow */ }
  return n;
}

export async function clearCrashes(): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY_CRASH_COUNT, '0');
    await AsyncStorage.setItem(KEY_LAST_CLEAN, String(Date.now()));
  } catch { /* swallow */ }
}

/**
 * bootGuard — call at app entry. Returns:
 *   'safe-mode'  if crash_count >= 2 (route to /safe-mode recovery screen)
 *   'normal'     otherwise
 *
 * Side effect: pre-increments crash_count so that if THIS boot crashes
 * before reaching `markBootClean()`, the next launch will see the new count.
 */
export async function bootGuard(): Promise<'safe-mode' | 'normal'> {
  const count = await getCrashCount();
  // 2026-06-24: threshold restored to 3 (was an aggressive 1). Now that the
  // root-cause OOM is fixed (lazy modals), a single transient crash — or a
  // stale counter left over from the pre-fix builds, or the user impatiently
  // force-closing during a slow/offline boot — must NOT trap them in Safe
  // Mode. Only a genuine CRASH LOOP (3 unclean boots in a row) routes there.
  // bootGuard pre-increments; markBootClean() resets to 0 the instant the Hub
  // paints, so real successful boots never accumulate.
  if (count < 3) {
    // Healthy range — pre-mark this boot as "in progress" so that if we crash
    // before reaching markBootClean(), the next launch sees the higher count.
    try { await AsyncStorage.setItem(KEY_CRASH_COUNT, String(count + 1)); } catch {}
    return 'normal';
  }
  // Crash-loop detected. ROOT-CAUSE FIX: clear the counter NOW so safe-mode is
  // shown at most once and the very next launch attempts a normal boot again.
  // Previously the counter was never reset on safe-mode entry, which
  // permanently locked the device out of the Hub (it kept re-routing to
  // safe-mode on every launch). The Hub's markBootClean() still resets on a
  // healthy boot; this just guarantees we never get stuck.
  try { await AsyncStorage.setItem(KEY_CRASH_COUNT, '0'); } catch {}
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { getFeatureFlag } = require('./featureFlags');
    if (getFeatureFlag('safe_mode_auto_route') === false) return 'normal';
  } catch { /* swallow — default to safe-mode if flag store unavailable */ }
  return 'safe-mode';
}

/** Mark this boot as clean — call once the app finishes initial mount. */
export async function markBootClean(): Promise<void> {
  await clearCrashes();
  await traceStep('boot_clean');
  // Track lifetime clean-boot count (diagnostics) — best effort.
  try {
    const prev = parseInt((await AsyncStorage.getItem('@boot/clean_count')) || '0', 10) || 0;
    await AsyncStorage.setItem('@boot/clean_count', String(prev + 1));
  } catch { /* swallow */ }
  // Upgraded bootstrap: kick the on-device self-cleaner AFTER a healthy boot,
  // non-blocking. Lazy import breaks the bootTracer↔selfCleaner cycle. Never
  // let cleanup failures affect the boot result.
  try {
    import('./selfCleaner')
      .then(m => m.runSelfCleaner('boot_clean'))
      .catch(() => {});
  } catch { /* swallow */ }
}

/** Wipes boot state (for "Reset & retry" buttons). */
export async function resetBootState(): Promise<void> {
  try {
    await AsyncStorage.multiRemove([KEY_TRACE, KEY_CRASH_COUNT, KEY_LAST_CLEAN]);
  } catch { /* swallow */ }
  _memoryTrace = [];
}

/** Read-only synchronous mirror of the in-process trace (since boot). */
export function getMemoryTrace(): TraceStep[] {
  return [..._memoryTrace];
}

export async function getLastCleanBoot(): Promise<number | null> {
  try {
    const v = await AsyncStorage.getItem(KEY_LAST_CLEAN);
    return v ? parseInt(v, 10) : null;
  } catch { return null; }
}
