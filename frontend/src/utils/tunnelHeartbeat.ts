/**
 * src/utils/tunnelHeartbeat.ts — probes /api/health and surfaces
 * a coarse status ("ok" | "degraded" | "down") via a tiny pub/sub.
 *
 * Intentionally low-frequency (15s) so it doesn't tax preview tunnels.
 * Adds jitter to avoid thundering-herd. Pauses while AppState !== 'active'.
 */
import { AppState, AppStateStatus } from 'react-native';
import api from './apiClient';
import { trail } from './breadcrumbs';

export type TunnelStatus = 'unknown' | 'ok' | 'degraded' | 'down';

type Listener = (s: TunnelStatus, extra: any) => void;

const POLL_BASE_MS = 15_000;
const POLL_JITTER_MS = 4_000;
const POLL_FAIL_MS = 5_000;       // re-check faster while a failure streak is building
const DOWN_THRESHOLD = 3;         // need 3 consecutive failures (~15s) before crying "down"

let _status: TunnelStatus = 'unknown';
let _last: any = null;
let _timer: ReturnType<typeof setTimeout> | null = null;
let _started = false;
let _inFlight = false;
let _generation = 0;
let _subscription: { remove: () => void } | null = null;
let _fails = 0;                   // consecutive heartbeat failures
const _listeners = new Set<Listener>();

function _emit() { _listeners.forEach(fn => { try { fn(_status, _last); } catch {} }); }

async function _poll() {
  if (!_started || AppState.currentState !== 'active') return;
  if (_inFlight) { _schedule(); return; }
  const generation = _generation;
  _inFlight = true;
  let failed = false;
  try {
    const r = await api.get<{ status?: string }>(
      '/api/health', { timeoutMs: 6_000, retries: 1 },
    );
    // Ignore an obsolete result *before* touching the published status.
    // A stopped observer must never revive itself after a slow request.
    if (generation !== _generation) {
      _inFlight = false;
      return;
    }
    if (r.ok && r.data) {
      _fails = 0;                                   // any success clears the streak
      // Passive tunnel inactivity does not establish current reachability.
      // Capability readiness remains owned by its separate service checks.
      const applicationStatus = typeof r.data.status === 'string' ? r.data.status.slice(0, 64) : null;
      const next: TunnelStatus = ['degraded', 'limited'].includes(applicationStatus || '') ? 'degraded' : 'ok';
      const observed = { probe: '/api/health', http_status: r.status, application_status: applicationStatus, observed_at: new Date().toISOString() };
      if (next !== _status) {
        trail.add('tunnel', `status:${_status} → ${next}`, observed, next === 'ok' ? 'info' : 'warn');
        _status = next;
        _last = observed;
        _emit();
      } else {
        _last = observed;
      }
    } else {
      failed = true;
    }
  } catch { failed = true; }

  if (generation !== _generation) {
    _inFlight = false;
    return; // An old request must not change state after stop/restart.
  }

  if (failed) {
    // A single slow/blipped heartbeat is NOT an outage — only flip to "down"
    // after DOWN_THRESHOLD consecutive failures so we never flash a false alarm.
    _fails += 1;
    if (_fails >= DOWN_THRESHOLD && _status !== 'down') {
      _status = 'down';
      _last = { gap_since_last_request_s: -1, error: `heartbeat failed ×${_fails}` };
      trail.add('tunnel', `down after ${_fails} consecutive fails`, {}, 'warn');
      _emit();
    }
  }
  _inFlight = false;
  _schedule(failed && _status !== 'down');
}

function _schedule(fast = false) {
  if (_timer) clearTimeout(_timer);
  if (!_started || AppState.currentState !== 'active') return;
  const base = fast ? POLL_FAIL_MS : POLL_BASE_MS;
  const jitter = Math.floor(Math.random() * POLL_JITTER_MS);
  _timer = setTimeout(_poll, base + jitter);
}

export function startTunnelHeartbeat(): void {
  if (_started) return;
  _started = true;
  _generation += 1;
  // Repoll on foreground transitions; one removable listener per root owner.
  try {
    _subscription = AppState.addEventListener('change', (s: AppStateStatus) => {
      if (!_started) return;
      if (s === 'active') void _poll();
      else if (_timer) { clearTimeout(_timer); _timer = null; }
    });
  } catch {
    _subscription = null;
  }
  if (AppState.currentState === 'active') void _poll();
}

export function stopTunnelHeartbeat(): void {
  if (!_started) return;
  _started = false;
  _generation += 1; // invalidate in-flight results without blocking teardown
  if (_timer) { clearTimeout(_timer); _timer = null; }
  try { _subscription?.remove(); } catch {}
  _subscription = null;
}

export function subscribeTunnel(fn: Listener): () => void {
  _listeners.add(fn);
  try { fn(_status, _last); } catch {}
  return () => { _listeners.delete(fn); };
}

export function getTunnelStatus(): TunnelStatus { return _status; }
export function getTunnelMeta(): any { return _last; }
