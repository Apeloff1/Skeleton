import { API_BASE as CANONICAL_API_BASE } from './apiBase';
import { scrubTelemetry } from './securityTelemetry';
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
import * as Crypto from 'expo-crypto';

const BACKEND  = CANONICAL_API_BASE;
const FLUSH_MS = 5000;
const QUEUE_KEY = '@telemetry/queue';

// One session id per app launch — persists across route changes.
let _sessionId: string | null = null;
function createSessionId(): string {
  // Telemetry identifiers can correlate user activity across screens.
  // Never use enumerable timestamps or counters as a fallback.
  return `s_${Crypto.randomUUID()}`;
}

function sessionId(): string {
  if (!_sessionId) {
    _sessionId = createSessionId();
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
    const raw = (await AsyncStorage.getItem(QUEUE_KEY)) || '[]';
    // Treat legacy offline telemetry as untrusted input: never parse a
    // multi-megabyte or malformed queue before restoring the byte budget.
    const existing = raw.length <= 2 * 1024 * 1024 ? JSON.parse(raw) : [];
    const previous = Array.isArray(existing) ? existing : [];
    const merged = [...previous.slice(-500), ...events].slice(-500);
    const sanitized = JSON.stringify(scrubTelemetry(merged));
    await AsyncStorage.setItem(QUEUE_KEY, sanitized.slice(0, 2 * 1024 * 1024));
  } catch { /* non-fatal */ }
}

async function _drainQueue(): Promise<TelemetryEvent[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    await AsyncStorage.removeItem(QUEUE_KEY);
    if (raw.length > 2 * 1024 * 1024) return [];
    const data = JSON.parse(raw);
    return (Array.isArray(data) ? (scrubTelemetry(data.slice(-500)) as TelemetryEvent[]) : []);
  } catch { return []; }
}

export async function flushTelemetry(): Promise<void> {
  if (_flushInflight) return;
  // Hold the lock *before* the first await. Two simultaneous flushes must not
  // drain or replay the same offline queue twice.
  _flushInflight = true;
  let safeBatch: TelemetryEvent[] = [];
  try {
    const queued = await _drainQueue();
    const batch = _buffer.splice(0, _buffer.length).concat(queued);
    if (!batch.length) return;
    // Scrub legacy queue contents too, not just new events.
    safeBatch = scrubTelemetry(batch) as TelemetryEvent[];
    const r = await fetch(`${BACKEND}/api/telemetry/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ events: safeBatch }),
    });
    if (!r.ok) await _persistQueue(safeBatch);
  } catch {
    // Preserve the original in-flight batch on network failure, but only
    // after scrubbing. Events that arrived during the request remain buffered.
    if (safeBatch.length) await _persistQueue(safeBatch);
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
    // Delayed load avoids a feature-flag/logger circular bootstrap.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { getFeatureFlag } = require('./featureFlags');
    if (getFeatureFlag('modal_telemetry_batch') === false) {
      if (severity === 'fatal' || severity === 'error') {
        // eslint-disable-next-line no-console
        console.warn('[telemetry:off] error event suppressed');
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
    detail: scrubTelemetry(detail),
  });
  if (_buffer.length > 500) _buffer.splice(0, _buffer.length - 500);
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
      // Raw exception messages and stacks routinely contain auth headers,
      // filesystem paths and private request data. Emit only the class name.
      const e = { name: err instanceof Error ? err.name : 'UnknownError',
                  message: 'client_operation_failed' };
      recordEvent(modalId, 'error', 'error', { ...e, details: detail });
    },
    raw:     (event: string, severity: Severity, detail?: any) => recordEvent(modalId, event, severity, detail),
  };
}

export function getSessionId(): string { return sessionId(); }
