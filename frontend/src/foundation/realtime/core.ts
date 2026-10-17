/**
 * Pure realtime core for the canonical SSE transport
 * (docs/architecture/ADR-realtime-transport.md, PR #4101).
 *
 * Dependency-free: SSE framing, envelope v1 parsing, resume cursor, liveness
 * and full-jitter backoff. The networked client composes these.
 */
export type Channel = 'build' | 'agent' | 'presence';
export const ALL_CHANNELS: readonly Channel[] = ['build', 'agent', 'presence'];

export interface Envelope<P = Record<string, unknown>> {
  v: number;
  id: string;
  ts: string;
  channel: string;
  type: string;
  payload: P;
  job_id?: string;
  correlation_id?: string;
}

/** Server writes `: hb` every 15s (`skeleton/realtime/sse.py`). Three misses and the stream is dead. */
export const HEARTBEAT_INTERVAL_MS = 15_000;
export const LIVENESS_TIMEOUT_MS = 45_000;
export const BACKOFF_BASE_MS = 500;
export const BACKOFF_MAX_MS = 30_000;
export const HEALTHY_RESET_MS = 60_000;
export const SUPPORTED_VERSION = 1;

// ── SSE framing ─────────────────────────────────────────────────────────
export interface SseFrame { id?: string; event: string; data: string; retry?: number }
export type SseItem = { kind: 'frame'; frame: SseFrame } | { kind: 'comment'; text: string };

/** Incremental text/event-stream parser (WHATWG rules: CRLF/CR/LF, multi-line data). */
export class SseParser {
  private buf = '';
  private data: string[] = [];
  private event = '';
  private id: string | undefined;
  private retry: number | undefined;

  feed(chunk: string): SseItem[] {
    this.buf += chunk;
    const out: SseItem[] = [];
    let idx: number;
    // eslint-disable-next-line no-cond-assign
    while ((idx = this.nextLineEnd()) >= 0) {
      const line = this.buf.slice(0, idx);
      const skip = this.buf[idx] === '\r' && this.buf[idx + 1] === '\n' ? 2 : 1;
      this.buf = this.buf.slice(idx + skip);
      this.line(line, out);
    }
    return out;
  }

  private nextLineEnd(): number {
    for (let i = 0; i < this.buf.length; i++) {
      const c = this.buf[i];
      if (c === '\n') return i;
      // A trailing CR may be the first half of CRLF: wait for more input.
      if (c === '\r') return i + 1 < this.buf.length ? i : -1;
    }
    return -1;
  }

  private line(line: string, out: SseItem[]) {
    if (line === '') {
      if (this.data.length) {
        out.push({ kind: 'frame', frame: { id: this.id, event: this.event || 'message', data: this.data.join('\n'), retry: this.retry } });
      }
      this.data = []; this.event = ''; this.retry = undefined;
      return;
    }
    if (line.startsWith(':')) { out.push({ kind: 'comment', text: line.slice(1).trim() }); return; }
    const colon = line.indexOf(':');
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'data') this.data.push(value);
    else if (field === 'event') this.event = value;
    else if (field === 'id') { if (!value.includes('\0')) this.id = value; }
    else if (field === 'retry') { if (/^\d+$/.test(value)) this.retry = Number(value); }
  }
}

// ── Envelope ────────────────────────────────────────────────────────────
export type ParseResult = { ok: true; envelope: Envelope } | { ok: false; reason: string };

function envelopeId(raw: unknown): string | null {
  if (typeof raw === 'string' && /^[0-9]{1,19}$/.test(raw) && !/^0+$/.test(raw)) return raw;
  if (typeof raw === 'number' && Number.isInteger(raw) && raw >= 1 && raw <= Number.MAX_SAFE_INTEGER) return String(raw);
  return null;
}

/**
 * Validate envelope v1. Unknown fields are dropped. `id` is the decimal string
 * from the envelope; when the SSE `id:` line is present it must match
 * (`sse_message_to_frame` raises on a mismatch). Optional ids are kept only
 * when they are strings.
 */
export function parseEnvelope(data: string | unknown, frameId?: string): ParseResult {
  let raw: unknown = data;
  if (typeof data === 'string') {
    try { raw = JSON.parse(data); } catch { return { ok: false, reason: 'invalid_json' }; }
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return { ok: false, reason: 'not_object' };
  const r = raw as Record<string, unknown>;
  if (typeof r.v !== 'number' || r.v !== SUPPORTED_VERSION) return { ok: false, reason: 'unsupported_version' };
  const id = envelopeId(r.id);
  if (!id) return { ok: false, reason: 'missing_id' };
  if (frameId && frameId !== id) return { ok: false, reason: 'id_mismatch' };
  if (typeof r.type !== 'string' || !r.type) return { ok: false, reason: 'missing_type' };
  if (typeof r.channel !== 'string' || !r.channel) return { ok: false, reason: 'missing_channel' };
  const payload = r.payload && typeof r.payload === 'object' && !Array.isArray(r.payload) ? (r.payload as Record<string, unknown>) : {};
  const env: Envelope = { v: r.v, id, ts: typeof r.ts === 'string' ? r.ts : '', channel: r.channel, type: r.type, payload };
  if (typeof r.job_id === 'string') env.job_id = r.job_id;
  if (typeof r.correlation_id === 'string') env.correlation_id = r.correlation_id;
  return { ok: true, envelope: env };
}

/** `x-gf-seal` for `/api/v1/events` and `/api/v1/presence`. Empty when the caller has no seal. */
export function realtimeAuthHeaders(seal: string | null | undefined): Record<string, string> {
  const token = typeof seal === 'string' ? seal.trim() : '';
  return token ? { 'x-gf-seal': token } : {};
}

// ── URL / resume ────────────────────────────────────────────────────────
export function buildStreamPath(opts: { channels: readonly Channel[]; jobId?: string | null; cursor?: string | null; useCursorParam?: boolean }): string {
  const channels = Array.from(new Set(opts.channels.filter(c => ALL_CHANNELS.includes(c)))).sort();
  const q = [`channels=${(channels.length ? channels : ALL_CHANNELS).join(',')}`];
  if (opts.jobId) q.push(`job_id=${encodeURIComponent(opts.jobId)}`);
  if (opts.cursor && opts.useCursorParam) q.push(`cursor=${encodeURIComponent(opts.cursor)}`);
  return `/api/v1/events?${q.join('&')}`;
}

export function resumeHeaders(cursor: string | null | undefined): Record<string, string> {
  return cursor ? { 'Last-Event-ID': cursor } : {};
}

// ── Backoff / liveness ──────────────────────────────────────────────────
/** Full-jitter exponential backoff: U(0, min(max, base·2^attempt)), floored by server `retry:`. */
export function backoffDelay(attempt: number, random: () => number = Math.random, retryFloorMs = 0): number {
  const cap = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * Math.pow(2, Math.max(0, attempt)));
  const jittered = Math.floor(Math.max(0, Math.min(1, random())) * cap);
  return Math.min(BACKOFF_MAX_MS, Math.max(jittered, BACKOFF_BASE_MS / 2, retryFloorMs || 0));
}

export function isStreamDead(lastActivityAt: number, now: number, timeoutMs = LIVENESS_TIMEOUT_MS): boolean {
  return now - lastActivityAt >= timeoutMs;
}

/** Attempts reset after a stream stays healthy for HEALTHY_RESET_MS. */
export function nextAttempt(attempt: number, connectedAt: number | null, now: number): number {
  if (connectedAt !== null && now - connectedAt >= HEALTHY_RESET_MS) return 0;
  return attempt + 1;
}

// ── Stream state reducer ────────────────────────────────────────────────
export type StreamStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed';
export interface StreamState {
  status: StreamStatus;
  cursor: string | null;
  lastActivityAt: number;
  connectedAt: number | null;
  attempt: number;
  retryFloorMs: number;
  lagged: number;
  resets: number;
  received: number;
  rejected: number;
}

export function initialStreamState(cursor: string | null = null): StreamState {
  return { status: 'idle', cursor, lastActivityAt: 0, connectedAt: null, attempt: 0, retryFloorMs: 0, lagged: 0, resets: 0, received: 0, rejected: 0 };
}

export type StreamEffect =
  | { kind: 'deliver'; envelope: Envelope }
  | { kind: 'reset' }
  | { kind: 'lagged'; dropped: number };

function controlPayload(data: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(data) as { payload?: unknown };
    const payload = parsed?.payload;
    if (payload && typeof payload === 'object' && !Array.isArray(payload)) return payload as Record<string, unknown>;
  } catch { /* control frames with no JSON payload leave the cursor alone */ }
  return {};
}

/** Apply one parsed SSE item; returns new state and effects for the client to run. */
export function applyItem(state: StreamState, item: SseItem, now: number): { state: StreamState; effects: StreamEffect[] } {
  const s: StreamState = { ...state, lastActivityAt: now };
  if (item.kind === 'comment') return { state: s, effects: [] };
  const { frame } = item;
  if (frame.retry !== undefined) s.retryFloorMs = Math.min(BACKOFF_MAX_MS, frame.retry);
  // Control frames are sent with no `id:` line, so they must not move Last-Event-ID.
  if (frame.event === 'stream.reset') {
    const head = controlPayload(frame.data).head_id;
    s.cursor = typeof head === 'string' && head ? head : null;
    s.resets += 1;
    return { state: s, effects: [{ kind: 'reset' }] };
  }
  if (frame.event === 'stream.lagged') {
    const payload = controlPayload(frame.data);
    const dropped = typeof payload.dropped === 'number' ? payload.dropped : 0;
    s.lagged += dropped || 1;
    if (s.cursor == null && typeof payload.resume_from === 'string' && payload.resume_from) {
      s.cursor = payload.resume_from;
    }
    return { state: s, effects: [{ kind: 'lagged', dropped }] };
  }
  const parsed = parseEnvelope(frame.data, frame.id);
  if (!parsed.ok) { s.rejected += 1; return { state: s, effects: [] }; }
  s.cursor = parsed.envelope.id;
  s.received += 1;
  return { state: s, effects: [{ kind: 'deliver', envelope: parsed.envelope }] };
}

// ── Build progress projection ───────────────────────────────────────────
export interface BuildProgress { jobId: string; status: 'running' | 'completed' | 'failed'; percent: number | null; message: string; updatedAt: string }

export function reduceBuildProgress(prev: Record<string, BuildProgress>, env: Envelope): Record<string, BuildProgress> {
  if (env.channel !== 'build' || !env.job_id) return prev;
  const p = env.payload as { pct?: unknown; percent?: unknown; progress?: unknown; message?: unknown; stage?: unknown };
  const pctRaw = typeof p.pct === 'number' ? p.pct : typeof p.percent === 'number' ? p.percent : typeof p.progress === 'number' ? (p.progress <= 1 ? p.progress * 100 : p.progress) : null;
  const percent = pctRaw === null ? prev[env.job_id]?.percent ?? null : Math.max(0, Math.min(100, Math.round(pctRaw)));
  const message = typeof p.message === 'string' ? p.message : typeof p.stage === 'string' ? p.stage : prev[env.job_id]?.message ?? '';
  let status: BuildProgress['status'] = 'running';
  if (env.type === 'build.completed') status = 'completed';
  else if (env.type === 'build.failed') status = 'failed';
  else if (env.type === 'build.log') status = prev[env.job_id]?.status ?? 'running';
  return { ...prev, [env.job_id]: { jobId: env.job_id, status, percent: status === 'completed' ? 100 : percent, message, updatedAt: env.ts } };
}
