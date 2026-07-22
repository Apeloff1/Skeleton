/**
 * globalGuards — JS-runtime safety nets installed once at app boot.
 *
 *   • Hooks `ErrorUtils.setGlobalHandler` (RN) to catch native-thread
 *     uncaught errors that escape React's render cycle. Posts to
 *     /api/telemetry/last-crash and logs into the boot trace.
 *   • Hooks unhandled promise rejections (`HermesInternal` /
 *     `process.on('unhandledRejection')` / window 'unhandledrejection')
 *     so a forgotten `.catch()` never silently bricks the app.
 *   • Optional: throttles the previous handler so floods of identical
 *     errors don't drown the telemetry endpoint.
 *
 * Call installGlobalGuards() ONCE from /app/_layout.tsx useEffect.
 * Safe to call multiple times — idempotent.
 */
import { traceStep } from './bootTracer';
import { getSessionId } from './modalLogger';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
let _installed = false;
const _seenHashes = new Set<string>();
const _MAX_SEEN = 50;

function postCrash(source: string, error: any, isFatal: boolean) {
  try {
    const message  = String(error?.message ?? error ?? 'unknown');
    const stack    = String(error?.stack ?? '').slice(0, 8000);
    const hash     = `${source}|${message.slice(0, 200)}`;
    if (_seenHashes.has(hash)) return;
    _seenHashes.add(hash);
    if (_seenHashes.size > _MAX_SEEN) {
      // Drop oldest by re-creating the set
      const arr = Array.from(_seenHashes).slice(-_MAX_SEEN / 2);
      _seenHashes.clear();
      arr.forEach(h => _seenHashes.add(h));
    }
    traceStep(`crash:${source}:${message.slice(0, 80)}`).catch(() => {});
    fetch(`${BACKEND}/api/telemetry/last-crash`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source,
        component:  source,
        message,
        stack,
        info:       { fatal: isFatal },
        session_id: getSessionId(),
      }),
    }).catch(() => {});
  } catch { /* never let the guard itself crash */ }
}

export function installGlobalGuards() {
  if (_installed) return;
  _installed = true;

  // ─── React-Native global error handler ───────────────────────────
  try {
    const ErrorUtils = (global as any).ErrorUtils;
    if (ErrorUtils && typeof ErrorUtils.setGlobalHandler === 'function') {
      const prev = ErrorUtils.getGlobalHandler?.();
      ErrorUtils.setGlobalHandler((error: any, isFatal: boolean) => {
        postCrash('ErrorUtils', error, !!isFatal);
        if (prev) try { prev(error, isFatal); } catch { /* swallow */ }
      });
    }
  } catch { /* swallow */ }

  // ─── Unhandled promise rejections (Hermes / web fallback) ───────
  try {
    if (typeof globalThis !== 'undefined' && 'addEventListener' in globalThis) {
      // Web/Node-ish runtimes (also fires on Hermes 0.12+).
      (globalThis as any).addEventListener('unhandledrejection', (ev: any) => {
        const reason = ev?.reason ?? ev;
        postCrash('unhandledrejection', reason, false);
      });
    }
  } catch { /* swallow */ }

  // ─── Node-style process listener (some RN builds expose this) ───
  try {
    const proc: any = (global as any).process;
    if (proc && typeof proc.on === 'function') {
      proc.on('unhandledRejection', (reason: any) => {
        postCrash('unhandledRejection', reason, false);
      });
    }
  } catch { /* swallow */ }

  traceStep('global_guards_installed').catch(() => {});
}
