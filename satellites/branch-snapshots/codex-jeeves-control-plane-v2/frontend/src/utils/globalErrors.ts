/**
 * src/utils/globalErrors.ts — install global JS error + promise-rejection
 * catchers and pipe them into the breadcrumb trail + telemetry.
 *
 * Idempotent: subsequent calls become no-ops. Designed to be invoked
 * once at app boot.
 */
import { Platform } from 'react-native';
import { trail } from './breadcrumbs';

let _installed = false;

function _record(category: string, message: string, data?: any) {
  try { trail.add(category, message, data || {}, 'error'); } catch { /* swallow */ }
  try { console.warn(`[globalErrors] ${category}: ${message}`); } catch {}
}

export function installGlobalErrorHandlers(): boolean {
  if (_installed) return false;
  _installed = true;

  // React Native: ErrorUtils provides the global JS error handler.
  try {
    const eu = (global as any).ErrorUtils;
    if (eu?.setGlobalHandler && eu?.getGlobalHandler) {
      const prev = eu.getGlobalHandler();
      eu.setGlobalHandler((err: Error, isFatal?: boolean) => {
        _record('js_error', String(err?.message || err), {
          stack: String(err?.stack || '').slice(0, 1024),
          fatal: !!isFatal,
        });
        try { prev?.(err, isFatal); } catch {}
      });
    }
  } catch {}

  // Web (and Hermes): unhandledRejection.
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      window.addEventListener('unhandledrejection', (e: any) => {
        _record('unhandled_rejection',
          String(e?.reason?.message || e?.reason || 'unknown'),
          { stack: String(e?.reason?.stack || '').slice(0, 1024) });
      });
      window.addEventListener('error', (e: any) => {
        _record('window_error', String(e?.message || 'unknown'), {
          src: String(e?.filename || ''), line: e?.lineno,
        });
      });
    } catch {}
  }
  trail.add('boot', 'globalErrorHandlers_installed', {}, 'info');
  return true;
}
