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
 *   - bootGuard() reads crash_count on app start. At >= 3, it retains
 *     the counter and sends the user to Safe Mode (unless opted out).
 *   - markBootClean() resets the counter after the product has rendered.
 *
 * NOTE: All AsyncStorage calls are best-effort. Never throws.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { LatestSnapshotWriter } from './LatestSnapshotWriter';
import { redactSecrets } from './safeError';

const KEY_TRACE       = '@boot/trace';
const KEY_SESSIONS    = '@boot/sessions';   // ring of previous sessions (crash-durable)
const MAX_SESSIONS    = 6;                   // keep last 6 session traces
const KEY_CRASH_COUNT = '@boot/crash_count';
const KEY_LAST_CLEAN  = '@boot/last_clean_boot';
const MAX_TRACE_LEN   = 150;
const STORAGE_READ_BUDGET_MS = 1_200;

function readStorageBounded(key: string): Promise<string | null> {
  return new Promise(resolve => {
    let settled = false;
    const finish = (value: string | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => finish(null), STORAGE_READ_BUDGET_MS);
    try { AsyncStorage.getItem(key).then(finish, () => finish(null)); }
    catch { finish(null); }
  });
}

/** Process-start epoch so every trace line carries a monotonic +Xms offset. */
const _T0 = Date.now();

export interface TraceStep {
  step: string;
  ts:   number;
}

let _memoryTrace: TraceStep[] = [];  // bounded in-process mirror
const TRACE_COALESCE_MS = 125;
let _flushTimer: ReturnType<typeof setTimeout> | null = null;
let _resetInProgress = false;

// Unlike a chained write promise, this never accumulates unbounded work
// when AsyncStorage stalls. Only one in-flight write and one latest snapshot
// are retained; session rotation precedes the first write.
const _traceWriter = new LatestSnapshotWriter(async serialized => {
  await _rotationReady;
  await AsyncStorage.setItem(KEY_TRACE, serialized);
});

function flushTrace(): void {
  if (_flushTimer !== null) {
    clearTimeout(_flushTimer);
    _flushTimer = null;
  }
  if (_resetInProgress) return;
  try { _traceWriter.enqueue(JSON.stringify(_memoryTrace)); } catch {}
}

function queueTraceFlush(step: string): void {
  if (_resetInProgress) return;
  const critical = /^(GLOBAL_ERROR|NAV_SAFE_MODE|UNHANDLED_REJECTION|boot_clean|crash:)/.test(step);
  if (critical) { flushTrace(); return; }
  if (_flushTimer === null) {
    _flushTimer = setTimeout(flushTrace, TRACE_COALESCE_MS);
  }
}

function boundedOperation(promise: Promise<unknown>, timeoutMs: number): Promise<boolean> {
  return new Promise(resolve => {
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) { settled = true; resolve(false); }
    }, timeoutMs);
    promise.then(
      () => { if (!settled) { settled = true; clearTimeout(timer); resolve(true); } },
      () => { if (!settled) { settled = true; clearTimeout(timer); resolve(false); } },
    );
  });
}

function traceLabel(step: string, extra?: Record<string, any>): string {
  try {
    const tail = extra ? ` ${JSON.stringify(extra).slice(0, 120)}` : '';
    return redactSecrets(`${step}${tail}`).slice(0, 240);
  } catch {
    return redactSecrets(String(step)).slice(0, 240);
  }
}

// ── Live trace pub/sub (drives the on-screen DevLogOverlay) ─────────────
type TraceListener = (t: TraceStep[]) => void;
const _listeners = new Set<TraceListener>();
let _notifyScheduled = false;
function _notify(): void {
  // Collapse bursts into one React notification; never update React during
  // another component's render or enqueue hundreds of hot-path setStates.
  if (_notifyScheduled) return;
  _notifyScheduled = true;
  const run = () => {
    _notifyScheduled = false;
    const snap = [..._memoryTrace];
    _listeners.forEach(l => { try { l(snap); } catch {} });
  };
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
  const label = traceLabel(step, extra);
  const row: TraceStep = { step: label, ts: Date.now() };
  _memoryTrace.push(row);
  if (_memoryTrace.length > MAX_TRACE_LEN) _memoryTrace = _memoryTrace.slice(-MAX_TRACE_LEN);
  // Console mirror — shows in Metro / `adb logcat` right up to a native
  // crash, the single most reliable trail for diagnosing device force-close.
  try { console.log(`[BOOTTRACE +${row.ts - _T0}ms] ${label}`); } catch {}
  _notify();
  try { queueTraceFlush(step); } catch { /* swallow */ }
}

/**
 * Synchronous trace — records to the in-memory mirror + console IMMEDIATELY
 * (no await), then flushes to AsyncStorage fire-and-forget. Use at hot paths
 * (module eval, render entry) where we can't await but still want the line
 * captured before a potential synchronous native crash.
 */
export function traceStepSync(step: string, extra?: Record<string, any>): void {
  const label = traceLabel(step, extra);
  const row: TraceStep = { step: label, ts: Date.now() };
  _memoryTrace.push(row);
  if (_memoryTrace.length > MAX_TRACE_LEN) _memoryTrace = _memoryTrace.slice(-MAX_TRACE_LEN);
  try { console.log(`[BOOTTRACE +${row.ts - _T0}ms] ${label}`); } catch {}
  _notify();
  try { queueTraceFlush(step); } catch {}
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
    const raw = await readStorageBounded(KEY_TRACE);
    if (!raw) return getMemoryTrace();
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(
      row => row && typeof row.step === 'string' && typeof row.ts === 'number',
    ).slice(-MAX_TRACE_LEN) as TraceStep[] : getMemoryTrace();
  } catch { return getMemoryTrace(); }
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
    const raw = await readStorageBounded(KEY_SESSIONS);
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
const _rotationReady = rotateSessionsOnce();

export async function getCrashCount(): Promise<number> {
  try {
    const v = await readStorageBounded(KEY_CRASH_COUNT);
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
  // A threshold crossing is NOT a clean boot. Keep the evidence until a
  // product screen renders successfully or the operator explicitly resets
  // startup state. Otherwise repeated crashes vanish from diagnostics.
  // Safe Mode exposes manual recovery, so there is no automatic lockout.
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
export async function resetBootState(): Promise<boolean> {
  if (_resetInProgress) return false;
  _resetInProgress = true;
  if (_flushTimer !== null) { clearTimeout(_flushTimer); _flushTimer = null; }
  try {
    // Do not delete storage while an older trace write is unresolved:
    // it could finish after removal and silently restore stale evidence.
    const idle = _traceWriter.pauseAndDiscard();
    if (!(await boundedOperation(idle, STORAGE_READ_BUDGET_MS))) return false;
    const removed = await boundedOperation(
      AsyncStorage.multiRemove([KEY_TRACE, KEY_CRASH_COUNT, KEY_LAST_CLEAN]),
      STORAGE_READ_BUDGET_MS,
    );
    if (!removed) return false;
    _memoryTrace = [];
    _notify();
    return true;
  } catch {
    return false;
  } finally {
    _traceWriter.resume();
    _resetInProgress = false;
  }
}

/** Read-only synchronous mirror of the in-process trace (since boot). */
export function getMemoryTrace(): TraceStep[] {
  return [..._memoryTrace];
}

export async function getLastCleanBoot(): Promise<number | null> {
  try {
    const v = await readStorageBounded(KEY_LAST_CLEAN);
    return v ? parseInt(v, 10) : null;
  } catch { return null; }
}
