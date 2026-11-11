import { API_BASE as CANONICAL_API_BASE } from './apiBase';
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
import {
  safeTelemetryErrorType, safeTelemetryEvent, safeTelemetryLabel,
  sanitizeTelemetryDetail,
} from './telemetryPrivacy';

const BACKEND  = CANONICAL_API_BASE;
const FLUSH_MS = 5000;
const QUEUE_KEY = '@telemetry/queue';
const MAX_QUEUE_BYTES = 1024 * 1024;
const MAX_EVENTS = 2000;

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
  detail?:     Record<string, string | number | boolean>;
}

// ─── Buffer + flusher ─────────────────────────────────────────────
const _buffer: TelemetryEvent[] = [];
let _flushTimer: ReturnType<typeof setInterval> | null = null;
let _flushInflight = false;

function sanitizeQueuedEvent(value: unknown): TelemetryEvent | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  // Old app versions wrote full exception objects to AsyncStorage. Strip all
  // foreign/untrusted fields both on restore and immediately before POST.
  const row = value as Record<string, unknown>;
  const severity = row.severity;
  const safeSeverity: Severity =
    severity === 'warn' || severity === 'error' || severity === 'fatal'
      ? severity : 'info';
  const timestamp = row.ts_client;
  const duration = row.duration_ms;
  return {
    modal_id: safeTelemetryLabel(row.modal_id),
    session_id: sessionId(),
    event: safeTelemetryEvent(row.event),
    severity: safeSeverity,
    ...(typeof timestamp === 'number' && Number.isFinite(timestamp) &&
        timestamp >= 0 && timestamp <= 10_000_000_000
      ? { ts_client: timestamp } : {}),
    ...(typeof duration === 'number' && Number.isFinite(duration) &&
        duration >= 0 && duration <= 86_400_000
      ? { duration_ms: duration } : {}),
    detail: sanitizeTelemetryDetail(row.detail),
  };
}

async function _persistQueue(events: TelemetryEvent[]) {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    let previous: unknown[] = [];
    if (raw && raw.length <= MAX_QUEUE_BYTES) {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) previous = parsed;
      } catch {
        // A corrupt legacy queue must not prevent today's safe diagnostics.
        previous = [];
      }
    }
    const merged = [...previous, ...events]
      .slice(-MAX_EVENTS)
      .map(sanitizeQueuedEvent)
      .filter((event): event is TelemetryEvent => event !== null);
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(merged));
  } catch { /* non-fatal; never log the queue content */ }
}

async function _drainQueue(): Promise<TelemetryEvent[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    await AsyncStorage.removeItem(QUEUE_KEY);
    if (raw.length > MAX_QUEUE_BYTES) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(-MAX_EVENTS).map(sanitizeQueuedEvent)
      .filter((event): event is TelemetryEvent => event !== null);
  } catch { return []; }
}

export async function flushTelemetry(): Promise<void> {
  if (_flushInflight) return;
  _flushInflight = true;
  let pending: TelemetryEvent[] = [];
  try {
    const queued = await _drainQueue();
    pending = _buffer.splice(0, _buffer.length)
      .concat(queued)
      .map(sanitizeQueuedEvent)
      .filter((event): event is TelemetryEvent => event !== null);
    // The backend admits at most 500 entries per batch. Split offline
    // backlogs into bounded requests and replay only the still-unsent tail.
    while (pending.length) {
      const part = pending.slice(0, 200);
      const r = await fetch(`${BACKEND}/api/telemetry/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events: part }),
      });
      if (!r.ok) break;
      pending = pending.slice(part.length);
    }
    if (pending.length) await _persistQueue(pending);
  } catch {
    if (pending.length) await _persistQueue(pending);
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
  // Network outages or blocked timers must not grow an unbounded in-memory
  // buffer; older diagnostics are less useful than current ones.
  if (_buffer.length >= MAX_EVENTS) {
    _buffer.splice(0, _buffer.length - MAX_EVENTS + 1);
  }
  _buffer.push({
    modal_id:   safeTelemetryLabel(modalId),
    session_id: sessionId(),
    event:      safeTelemetryEvent(event),
    severity,
    ts_client:  Date.now() / 1000,
    duration_ms: typeof duration_ms === 'number' &&
      Number.isFinite(duration_ms) && duration_ms >= 0 && duration_ms <= 86_400_000
      ? duration_ms : undefined,
    detail: sanitizeTelemetryDetail(detail),
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
      // Never include raw exception message or stack: they may contain URL
      // credentials, user text, prompts or private local filesystem paths.
      recordEvent(modalId, 'error', 'error', {
        error_type: safeTelemetryErrorType(err), ...detail,
      });
    },
    raw:     (event: string, severity: Severity, detail?: any) => recordEvent(modalId, event, severity, detail),
  };
}

export function getSessionId(): string { return sessionId(); }
