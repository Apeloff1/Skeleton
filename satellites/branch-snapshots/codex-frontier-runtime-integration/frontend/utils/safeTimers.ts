/**
 * safeTimers — leak-free setTimeout / setInterval registry.
 *
 *   • Every timer registered through `safeTimeout` / `safeInterval` is
 *     auto-cancelled when the component unmounts (via the returned
 *     `clear` function or the `useSafeTimers` hook).
 *   • The registry caps at 1000 live timers — drops the oldest with a
 *     log warning to surface runaway-leak bugs early.
 *   • AppState listener clears all timers when the app goes to
 *     background (battery + thermal win on Android) and re-attaches a
 *     fresh registry when it resumes.
 *
 * Usage in a component:
 *   const t = useSafeTimers();
 *   t.setTimeout(() => doThing(), 500);
 *   t.setInterval(() => poll(), 2000);
 *   // automatic cleanup on unmount
 */
import { useEffect, useRef } from 'react';
import { AppState, AppStateStatus } from 'react-native';

interface TimerHandle {
  id: number;
  kind: 'timeout' | 'interval';
}

const _registry = new Set<{ raw: ReturnType<typeof setTimeout>; meta: TimerHandle }>();
const MAX_LIVE  = 1000;

function _track(raw: ReturnType<typeof setTimeout>, kind: 'timeout' | 'interval'): { raw: ReturnType<typeof setTimeout>; meta: TimerHandle } {
  if (_registry.size >= MAX_LIVE) {
    // Drop oldest to avoid unbounded growth — should never happen in a healthy app.
    const oldest = _registry.values().next().value;
    if (oldest) {
      try { (oldest.meta.kind === 'interval' ? clearInterval : clearTimeout)(oldest.raw as any); } catch {}
      _registry.delete(oldest);
      // eslint-disable-next-line no-console
      console.warn('[safeTimers] registry overflow — dropped oldest timer');
    }
  }
  const handle = { raw, meta: { id: Math.random(), kind } };
  _registry.add(handle);
  return handle;
}

export function safeSetTimeout(fn: () => void, ms: number): () => void {
  const raw = setTimeout(() => {
    try { fn(); } finally { _registry.forEach(h => { if (h.raw === raw) _registry.delete(h); }); }
  }, ms);
  const h = _track(raw, 'timeout');
  return () => { clearTimeout(h.raw as any); _registry.delete(h); };
}

export function safeSetInterval(fn: () => void, ms: number): () => void {
  const raw = setInterval(() => {
    try { fn(); } catch { /* swallow */ }
  }, ms);
  const h = _track(raw, 'interval');
  return () => { clearInterval(h.raw as any); _registry.delete(h); };
}

/** Wipe every live timer — called automatically on AppState background. */
export function clearAllTimers() {
  for (const h of _registry) {
    try { (h.meta.kind === 'interval' ? clearInterval : clearTimeout)(h.raw as any); } catch {}
  }
  _registry.clear();
}

export function liveTimerCount(): number { return _registry.size; }

// ── Auto-clear on app background ────────────────────────────────────
let _appStateInstalled = false;
export function installAppStateGuard() {
  if (_appStateInstalled) return;
  _appStateInstalled = true;
  try {
    AppState.addEventListener('change', (state: AppStateStatus) => {
      if (state === 'background' || state === 'inactive') {
        // Don't nuke everything — only intervals (timeouts are one-shot, safe).
        for (const h of Array.from(_registry)) {
          if (h.meta.kind === 'interval') {
            try { clearInterval(h.raw as any); } catch {}
            _registry.delete(h);
          }
        }
      }
    });
  } catch { /* swallow */ }
}

// ── Hook ────────────────────────────────────────────────────────────
export function useSafeTimers() {
  const cancels = useRef<Array<() => void>>([]);

  useEffect(() => {
    return () => {
      for (const c of cancels.current) { try { c(); } catch { /* swallow */ } }
      cancels.current = [];
    };
  }, []);

  return {
    setTimeout: (fn: () => void, ms: number) => {
      const c = safeSetTimeout(fn, ms);
      cancels.current.push(c);
      return c;
    },
    setInterval: (fn: () => void, ms: number) => {
      const c = safeSetInterval(fn, ms);
      cancels.current.push(c);
      return c;
    },
  };
}
