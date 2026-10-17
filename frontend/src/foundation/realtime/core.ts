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

/** Validate envelope v1; unknown fields are dropped, optional fields kept only when strings. */
export function parseEnvelope(data: string | unknown, frameId?: string): ParseResult {
  let raw: unknown = data;
  if (typeof data === 'string') {
    try { raw = JSON.parse(data); } catch { return { ok: false, reason: 'invalid_json' }; }
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return { ok: false, reason: 'not_object' };
  const r = raw as Record<string, unknown>;
  if (typeof r.v !== 'number' || r.v !== SUPPORTED_VERSION) return { ok: false, reason: 'unsupported_version' };
  const id = typeof r.id === 'string' && r.id ? r.id : typeof r.id === 'number' ? String(r.id) : frameId;
  if (!id) return { ok: false, reason: 'missing_id' };
  if (typeof r.type !== 'string' || !r.type) return { ok: false, reason: 'missing_type' };
  if (typeof r.channel !== 'string' || !r.channel) return { ok: false, reason: 'missing_channel' };
  const payload = r.payload && typeof r.payload === 'object' && !Array.isArray(r.payload) ? (r.payload as Record<string, unknown>) : {};
  const env: Envelope = { v: r.v, id, ts: typeof r.ts === 'string' ? r.ts : '', channel: r.channel, type: r.type, payload };
  if (typeof r.job_id === 'string') env.job_id = r.job_id;
  if (typeof r.correlation_id === 'string') env.correlation_id = r.correlation_id;
  return { ok: true, envelope: env };
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

/** Apply one parsed SSE item; returns new state and effects for the client to run. */
export function applyItem(state: StreamState, item: SseItem, now: number): { state: StreamState; effects: StreamEffect[] } {
  const s: StreamState = { ...state, lastActivityAt: now };
  if (item.kind === 'comment') return { state: s, effects: [] };
  const { frame } = item;
  if (frame.retry !== undefined) s.retryFloorMs = Math.min(BACKOFF_MAX_MS, frame.retry);
  if (frame.event === 'stream.reset') {
    s.cursor = null; s.resets += 1;
    return { state: s, effects: [{ kind: 'reset' }] };
  }
  if (frame.event === 'stream.lagged') {
    let dropped = 0;
    try { const d = JSON.parse(frame.data); const n = d?.payload?.dropped ?? d?.dropped; dropped = typeof n === 'number' ? n : 0; } catch {}
    s.lagged += dropped || 1;
    if (frame.id) s.cursor = frame.id;
    return { state: s, effects: [{ kind: 'lagged', dropped }] };
  }
  const parsed = parseEnvelope(frame.data, frame.id);
  if (!parsed.ok) { s.rejected += 1; return { state: s, effects: [] }; }
  s.cursor = frame.id || parsed.envelope.id;
  s.received += 1;
  return { state: s, effects: [{ kind: 'deliver', envelope: parsed.envelope }] };
}

// ── Build progress projection ───────────────────────────────────────────
export interface BuildProgress { jobId: string; status: 'running' | 'completed' | 'failed'; percent: number | null; message: string; updatedAt: string }

export function reduceBuildProgress(prev: Record<string, BuildProgress>, env: Envelope): Record<string, BuildProgress> {
  if (env.channel !== 'build' || !env.job_id) return prev;
  const p = env.payload as { percent?: unknown; progress?: unknown; message?: unknown; stage?: unknown };
  const pctRaw = typeof p.percent === 'number' ? p.percent : typeof p.progress === 'number' ? (p.progress <= 1 ? p.progress * 100 : p.progress) : null;
  const percent = pctRaw === null ? prev[env.job_id]?.percent ?? null : Math.max(0, Math.min(100, Math.round(pctRaw)));
  const message = typeof p.message === 'string' ? p.message : typeof p.stage === 'string' ? p.stage : prev[env.job_id]?.message ?? '';
  let status: BuildProgress['status'] = 'running';
  if (env.type === 'build.completed') status = 'completed';
  else if (env.type === 'build.failed') status = 'failed';
  else if (env.type === 'build.log') status = prev[env.job_id]?.status ?? 'running';
  return { ...prev, [env.job_id]: { jobId: env.job_id, status, percent: status === 'completed' ? 100 : percent, message, updatedAt: env.ts } };
}
