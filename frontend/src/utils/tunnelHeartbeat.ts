/**
 * src/utils/tunnelHeartbeat.ts — polls /api/health/tunnel and surfaces
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
let _fails = 0;                   // consecutive heartbeat failures
const _listeners = new Set<Listener>();

function _emit() { _listeners.forEach(fn => { try { fn(_status, _last); } catch {} }); }

async function _poll() {
  let failed = false;
  try {
    const r = await api.get<{ status: TunnelStatus; gap_since_last_request_s?: number; flap_count_total?: number }>(
      '/api/health/tunnel', { timeoutMs: 6_000, retries: 1 },
    );
    if (r.ok && r.data) {
      _fails = 0;                                   // any success clears the streak
      const next = (r.data.status || 'unknown') as TunnelStatus;
      if (next !== _status) {
        trail.add('tunnel', `status:${_status} → ${next}`, r.data as any, next === 'ok' ? 'info' : 'warn');
        _status = next;
        _last = r.data;
        _emit();
      } else {
        _last = r.data;
      }
    } else {
      failed = true;
    }
  } catch { failed = true; }

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
  _schedule(failed && _status !== 'down');
}

function _schedule(fast = false) {
  if (_timer) clearTimeout(_timer);
  if (AppState.currentState !== 'active') return;
  const base = fast ? POLL_FAIL_MS : POLL_BASE_MS;
  const jitter = Math.floor(Math.random() * POLL_JITTER_MS);
  _timer = setTimeout(_poll, base + jitter);
}

export function startTunnelHeartbeat(): void {
  if (_started) return;
  _started = true;
  // Repoll on foreground transitions.
  AppState.addEventListener('change', (s: AppStateStatus) => {
    if (s === 'active') _poll();
    else if (_timer) { clearTimeout(_timer); _timer = null; }
  });
  _poll();
}

export function subscribeTunnel(fn: Listener): () => void {
  _listeners.add(fn);
  try { fn(_status, _last); } catch {}
  return () => { _listeners.delete(fn); };
}

export function getTunnelStatus(): TunnelStatus { return _status; }
export function getTunnelMeta(): any { return _last; }
