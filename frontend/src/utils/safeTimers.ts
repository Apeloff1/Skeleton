/**
 * Lifecycle-aware timer ownership for long-running native/web sessions.
 *
 * Intervals are suspended while the app is inactive and automatically
 * rearmed on foreground, rather than permanently disappearing. A busy
 * async callback is never overlapped and its rejection is contained.
 * Hook-owned timer disposers are removed as soon as a timeout fires.
 */
import { useEffect, useRef } from 'react';
import { AppState, type AppStateStatus } from 'react-native';

type Task = () => void | Promise<unknown>;
type Kind = 'timeout' | 'interval';
interface Handle {
  kind: Kind;
  fn: Task;
  delay: number;
  raw: ReturnType<typeof setTimeout> | null;
  cancelled: boolean;
  running: boolean;
  onDone?: () => void;
}
const registry = new Set<Handle>();
const MAX_LIVE = 1000;
// RN can report "unknown" during native bridge startup. Until the OS
// confirms an inactive/background state, allow foreground timer work.
let activeState: AppStateStatus = AppState.currentState === 'background' ||
  AppState.currentState === 'inactive' ? AppState.currentState : 'active';
let subscription: { remove: () => void } | null = null;
let installed = false;

function boundedDelay(ms: number, fallback: number): number {
  return Number.isFinite(ms)
    ? Math.max(1, Math.min(2_147_483_647, Math.trunc(ms)))
    : fallback;
}
function dispose(handle: Handle): void {
  if (handle.cancelled) return;
  handle.cancelled = true;
  if (handle.raw !== null) {
    if (handle.kind === 'interval') clearInterval(handle.raw);
    else clearTimeout(handle.raw);
  }
  handle.raw = null;
  registry.delete(handle);
  const done = handle.onDone;
  handle.onDone = undefined;
  try { done?.(); } catch { /* cleanup cannot crash scheduler */ }
}
function invoke(handle: Handle): void {
  if (handle.cancelled || handle.running) return;
  handle.running = true;
  let outcome: void | Promise<unknown>;
  try { outcome = handle.fn(); }
  catch (error) {
    console.warn('[safeTimers] timer callback failed', error);
    handle.running = false;
    return;
  }
  // Explicit handlers on both outcomes avoid detached rejected promises.
  void Promise.resolve(outcome).then(
    () => { handle.running = false; },
    error => {
      handle.running = false;
      console.warn('[safeTimers] async timer callback failed', error);
    },
  );
}
function arm(handle: Handle): void {
  if (handle.cancelled || handle.raw !== null) return;
  if (handle.kind === 'interval') {
    if (activeState !== 'active') return;
    handle.raw = setInterval(() => invoke(handle), handle.delay);
  } else {
    handle.raw = setTimeout(() => {
      // Clear ownership before running user code, including throwing code.
      if (handle.cancelled) return;
      dispose(handle);
      invokeAfterDisposal(handle.fn);
    }, handle.delay);
  }
}
function invokeAfterDisposal(fn: Task): void {
  try {
    const result = fn();
    void Promise.resolve(result).then(undefined, error => {
      console.warn('[safeTimers] async timeout callback failed', error);
    });
  } catch (error) {
    console.warn('[safeTimers] timeout callback failed', error);
  }
}
function track(handle: Handle): () => void {
  if (registry.size >= MAX_LIVE) {
    const oldest = registry.values().next().value;
    if (oldest) dispose(oldest);
    console.warn('[safeTimers] registry saturated; evicted oldest task');
  }
  registry.add(handle);
  arm(handle);
  return () => dispose(handle);
}
export function safeSetTimeout(fn: Task, ms: number): () => void {
  return track({
    kind: 'timeout', fn, delay: boundedDelay(ms, 300),
    raw: null, cancelled: false, running: false,
  });
}
export function safeSetInterval(fn: Task, ms: number): () => void {
  return track({
    kind: 'interval', fn, delay: boundedDelay(ms, 1000),
    raw: null, cancelled: false, running: false,
  });
}
export function clearAllTimers(): void {
  for (const handle of [...registry]) dispose(handle);
}
export function liveTimerCount(): number { return registry.size; }
export function safeTimerStats() {
  return {
    registered: registry.size,
    armed: [...registry].filter(h => h.raw !== null).length,
    suspended: [...registry].filter(h => h.kind === 'interval' && h.raw === null).length,
  };
}
export function installAppStateGuard(): void {
  if (installed) return;
  try {
    const current = AppState.currentState;
    activeState = current === 'background' || current === 'inactive' ? current : 'active';
    // Reconcile registrations created while the bridge was unavailable.
    for (const handle of [...registry]) {
      if (handle.kind !== 'interval') continue;
      if (activeState === 'active') arm(handle);
      else if (handle.raw !== null) {
        clearInterval(handle.raw);
        handle.raw = null;
      }
    }
    subscription = AppState.addEventListener('change', state => {
      activeState = state;
      for (const handle of [...registry]) {
        if (handle.kind !== 'interval' || handle.cancelled) continue;
        if (state !== 'active') {
          if (handle.raw !== null) clearInterval(handle.raw);
          handle.raw = null;
        } else {
          arm(handle);
        }
      }
    });
    installed = true;
  } catch {
    subscription = null;
  }
}
export function uninstallAppStateGuard(): void {
  subscription?.remove();
  subscription = null;
  installed = false;
  // No more reliable native state events. Do not leave a stale inactive
  // state permanently suppressing future intervals after hot reload.
  activeState = AppState.currentState === 'background' ||
    AppState.currentState === 'inactive' ? AppState.currentState : 'active';
  if (activeState === 'active') {
    for (const handle of [...registry]) if (handle.kind === 'interval') arm(handle);
  }
}
/** Return a stable timer scope and cancel all owned tasks after unmount. */
export function useSafeTimers() {
  const owned = useRef(new Set<() => void>());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const ownedTimers = owned.current;
    return () => {
      mounted.current = false;
      for (const cancel of [...ownedTimers]) cancel();
      ownedTimers.clear();
    };
  }, []);
  function schedule(fn: Task, ms: number, kind: Kind): () => void {
    if (!mounted.current) return () => {};
    let release = () => {};
    const wrapped = () => {
      if (kind === 'timeout') owned.current.delete(release);
      if (!mounted.current) return;
      return fn();
    };
    const cancel = kind === 'interval'
      ? safeSetInterval(wrapped, ms) : safeSetTimeout(wrapped, ms);
    release = () => { cancel(); owned.current.delete(release); };
    owned.current.add(release);
    return release;
  }
  return {
    setTimeout: (fn: Task, ms: number) => schedule(fn, ms, 'timeout'),
    setInterval: (fn: Task, ms: number) => schedule(fn, ms, 'interval'),
  };
}
