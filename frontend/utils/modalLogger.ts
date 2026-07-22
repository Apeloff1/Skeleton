/**
 * modalLogger — per-modal telemetry tracker.
 *
 * Usage:
 *   const log = useModalLogger('GalaxyStudioFactoryModal');
 *   log.open();                           // on mount
 *   log.action('packageBuild_clicked', { kind: 'apk' });
 *   log.error(new Error(...));            // any caught throwable
 *   log.metric('build_duration_ms', 2400);
 *   log.close();                          // on unmount
 *
 * Events are buffered locally and POSTed to /api/telemetry/batch every 5s
 * (or on close). If offline, queued in AsyncStorage and flushed on reconnect.
 */
import { useEffect, useMemo, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const BACKEND  = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const FLUSH_MS = 5000;
const QUEUE_KEY = '@telemetry/queue';

// One session id per app launch — persists across route changes.
let _sessionId: string | null = null;
function sessionId(): string {
  if (!_sessionId) {
    _sessionId = `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  }
  return _sessionId;
}

export type Severity = 'info' | 'warn' | 'error' | 'fatal';
export interface TelemetryEvent {
  modal_id:    string;
  session_id:  string;
  event:       string;
  severity:    Severity;
  ts_client?:  number;
  duration_ms?: number;
  detail?:     any;
}

// ─── Buffer + flusher ─────────────────────────────────────────────
const _buffer: TelemetryEvent[] = [];
let _flushTimer: ReturnType<typeof setInterval> | null = null;
let _flushInflight = false;

async function _persistQueue(events: TelemetryEvent[]) {
  try {
    const existing = JSON.parse((await AsyncStorage.getItem(QUEUE_KEY)) || '[]');
    const merged = [...existing, ...events].slice(-2000);
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(merged));
  } catch { /* non-fatal */ }
}

async function _drainQueue(): Promise<TelemetryEvent[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    await AsyncStorage.removeItem(QUEUE_KEY);
    return JSON.parse(raw) as TelemetryEvent[];
  } catch { return []; }
}

export async function flushTelemetry(): Promise<void> {
  if (_flushInflight) return;
  const queued = await _drainQueue();
  const batch = _buffer.splice(0, _buffer.length).concat(queued);
  if (!batch.length) return;
  _flushInflight = true;
  try {
    const r = await fetch(`${BACKEND}/api/telemetry/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ events: batch }),
    });
    if (!r.ok) await _persistQueue(batch);
  } catch {
    await _persistQueue(batch);
  } finally {
    _flushInflight = false;
  }
}

function _startFlusher() {
  if (_flushTimer) return;
  _flushTimer = setInterval(() => { flushTelemetry().catch(() => {}); }, FLUSH_MS);
}

export function recordEvent(
  modalId: string,
  event: string,
  severity: Severity = 'info',
  detail?: any,
  duration_ms?: number,
) {
  // Honour the modal_telemetry_batch feature flag — disabling kills the
  // batched POSTs entirely (errors/fatals still get a console signal).
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { getFeatureFlag } = require('./featureFlags');
    if (getFeatureFlag('modal_telemetry_batch') === false) {
      if (severity === 'fatal' || severity === 'error') {
        // eslint-disable-next-line no-console
        console.warn(`[telemetry:off] ${modalId} ${event}`, detail);
      }
      return;
    }
  } catch { /* swallow — proceed with buffering */ }
  _buffer.push({
    modal_id:   modalId,
    session_id: sessionId(),
    event,
    severity,
    ts_client:  Date.now() / 1000,
    duration_ms,
    detail,
  });
  _startFlusher();
  // Force-flush fatals immediately
  if (severity === 'fatal' || severity === 'error') {
    flushTelemetry().catch(() => {});
  }
}

// ─── Public hook ──────────────────────────────────────────────────
export function useModalLogger(modalId: string) {
  const openedAt = useRef<number | null>(null);
  const sid = useMemo(() => sessionId(), []);

  useEffect(() => {
    openedAt.current = Date.now();
    recordEvent(modalId, 'open');
    return () => {
      const dur = openedAt.current ? Date.now() - openedAt.current : undefined;
      recordEvent(modalId, 'close', 'info', undefined, dur);
      flushTelemetry().catch(() => {});
    };
  }, [modalId]);

  return {
    sessionId: sid,
    action:  (name: string, detail?: any)               => recordEvent(modalId, `action:${name}`, 'info', detail),
    nav:     (to: string)                               => recordEvent(modalId, 'nav', 'info', { to }),
    metric:  (name: string, value: number, unit?: string)=> recordEvent(modalId, `metric:${name}`, 'info', { value, unit }),
    warn:    (msg: string, detail?: any)                => recordEvent(modalId, 'warn', 'warn', { msg, ...detail }),
    error:   (err: any, detail?: any)                   => {
      const e = err instanceof Error ? { name: err.name, message: err.message, stack: err.stack?.slice(0, 4000) } : { message: String(err) };
      recordEvent(modalId, 'error', 'error', { ...e, ...detail });
    },
    raw:     (event: string, severity: Severity, detail?: any) => recordEvent(modalId, event, severity, detail),
  };
}

export function getSessionId(): string { return sessionId(); }
