/**
 * Single best-effort sender for the existing crash endpoint.
 *
 * A fatal error can be caught by several nested boundaries. Bound concurrent
 * submissions, duplicate reports, payload size and each network attempt so
 * observability itself cannot become a crash amplifier. Never retries.
 */
import { API_BASE } from './apiBase';

const ENDPOINT = `${API_BASE}/api/telemetry/last-crash`;
const TIMEOUT_MS = 2_500;
const WINDOW_MS = 60_000;
const MAX_REPORTS_PER_WINDOW = 12;
const MAX_CONCURRENT = 2;
const MAX_PAYLOAD_CHARS = 8_192;
const DEDUPE_MS = 10_000;

let windowStart = 0;
let sent = 0;
let inFlight = 0;
const recent = new Map<string, number>();

export function postCrashReport(payload: Record<string, unknown>): boolean {
  const now = Date.now();
  if (now - windowStart >= WINDOW_MS || now < windowStart) {
    windowStart = now;
    sent = 0;
    recent.clear();
  }
  if (sent >= MAX_REPORTS_PER_WINDOW || inFlight >= MAX_CONCURRENT) return false;
  const identity = `${String(payload.component ?? '').slice(0, 100)}|${String(payload.message ?? '').slice(0, 200)}`;
  const previous = recent.get(identity);
  if (previous !== undefined && now - previous < DEDUPE_MS) return false;

  let serialized: string;
  try {
    serialized = JSON.stringify(payload);
    if (serialized.length > MAX_PAYLOAD_CHARS) return false;
  } catch {
    return false;
  }
  recent.set(identity, now);
  if (recent.size > 32) {
    const oldest = recent.keys().next().value;
    if (oldest !== undefined) recent.delete(oldest);
  }
  sent += 1;
  inFlight += 1;

  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const request = Promise.resolve().then(() => fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: serialized,
      signal: ctrl?.signal,
    })).then(() => undefined, () => undefined);
    const deadline = new Promise<void>(resolve => {
      timer = setTimeout(() => {
        try { ctrl?.abort(); } catch {}
        resolve();
      }, TIMEOUT_MS);
    });
    void Promise.race([request, deadline]).finally(() => {
      if (timer !== null) clearTimeout(timer);
      inFlight = Math.max(0, inFlight - 1);
    });
    return true;
  } catch {
    if (timer !== null) clearTimeout(timer);
    inFlight = Math.max(0, inFlight - 1);
    return false;
  }
}
