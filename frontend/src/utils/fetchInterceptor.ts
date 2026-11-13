/**
 * fetchInterceptor — global `fetch` wrapper that routes every request
 * (from any modal, feature, or component) through the SOTA API controller.
 *
 * This is the migration shortcut: instead of refactoring 30+ feature files,
 * we install a one-time monkey-patch at app boot. After install, every
 * `fetch(API_BASE + '/api/...')` automatically gets:
 *   • request-id propagation (X-Request-Id header echoed)
 *   • exponential-backoff retries on 5xx / network errors
 *   • request deduplication for GET
 *   • telemetry counters in apiController.getTelemetry()
 *   • timeout via AbortController (15 s default)
 *
 * Non-API URLs (Expo asset URLs, image CDNs, etc.) bypass the controller
 * and use the native fetch unchanged.
 *
 * IDEMPOTENT — safe to import multiple times. The first import installs;
 * subsequent imports are no-ops.
 */
import { api } from './apiController';

const _GLOBAL = (typeof globalThis !== 'undefined' ? globalThis : (global as any));
let _installed = false;

/** Predicate: does this URL look like one of OUR backend API endpoints? */
function _isOurApi(url: string): boolean {
  // Accept /api/... relative paths or absolute URLs ending in /api/...
  if (!url) return false;
  if (url.startsWith('/api/')) return true;
  // Absolute URLs — only intercept when the path contains /api/.
  return /\/api\//.test(url);
}

/** Convert a Headers-like input to a plain record. */
function _headersToRecord(h: any): Record<string, string> {
  if (!h) return {};
  if (typeof h.forEach === 'function') {
    const out: Record<string, string> = {};
    h.forEach((v: string, k: string) => { out[k] = v; });
    return out;
  }
  if (Array.isArray(h)) {
    return Object.fromEntries(h);
  }
  return { ...h };
}

export function installFetchInterceptor() {
  if (_installed) return;
  if (typeof _GLOBAL.fetch !== 'function') return;

  // Stash the original fetch on a well-known property so apiController can
  // use it for its internal HTTP calls — avoids infinite recursion when the
  // controller does fetch(...) which would otherwise be re-intercepted.
  if (!_GLOBAL.__origFetch) _GLOBAL.__origFetch = _GLOBAL.fetch.bind(_GLOBAL);
  const _origFetch = _GLOBAL.__origFetch;

  _GLOBAL.fetch = async (input: any, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : (input?.url || '');
    // Only intercept our API. Everything else passes through cleanly.
    if (!_isOurApi(url)) return _origFetch(input, init);

    // If the caller passed an AbortSignal, RESPECT IT by passing through
    // to native fetch. The apiController's own retry/timeout machinery
    // would override the caller's intent and could hang the boot path
    // (e.g. tripleBufferFetch sets a 5s LIVE_TIMEOUT_MS via AbortController).
    if (init?.signal) return _origFetch(input, init);

    const method = (init?.method || 'GET').toUpperCase();
    const headers = _headersToRecord(init?.headers);

    // Parse body if it's a JSON string (matches the original API surface).
    let parsedBody: any = init?.body;
    if (typeof parsedBody === 'string') {
      try { parsedBody = JSON.parse(parsedBody); } catch { /* keep as string */ }
    }

    try {
      const data: any = await (api as any)[method.toLowerCase()]?.(
        url,
        method === 'GET' || method === 'DELETE' ? { headers } : parsedBody,
        method === 'GET' || method === 'DELETE' ? undefined : { headers },
      ) ?? await (api as any).get(url, { headers });

      // Re-shape into a Response so existing callers `r.ok` / `r.json()` keep working.
      return new Response(JSON.stringify(data ?? null), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    } catch (e: any) {
      // Mirror the original HTTP semantics: produce a non-ok Response so callers
      // that check `r.ok` still see a failure (without throwing).
      const status = typeof e?.status === 'number' && e.status > 0 ? e.status : 500;
      const body = e?.body !== undefined ? e.body : { error: e?.message || 'Request failed', code: e?.code };
      return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      });
    }
  };

  _installed = true;
}
