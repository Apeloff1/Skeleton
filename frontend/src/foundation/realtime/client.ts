/**
 * EventStreamClient — connection lifecycle for the canonical SSE stream:
 * resume (Last-Event-ID, or ?cursor= when headers are unavailable), 45 s
 * liveness watchdog, full-jitter backoff 0.5–30 s (reset after 60 s healthy,
 * server `retry:` honoured as floor), stream.reset / stream.lagged handling.
 *
 * Transport and clock are injected, so this file has no platform imports and
 * is unit-tested with a mock server.
 */
import {
  applyItem, backoffDelay, buildStreamPath, Channel, Envelope, initialStreamState, isStreamDead,
  LIVENESS_TIMEOUT_MS, nextAttempt, resumeHeaders, SseParser, StreamState,
} from './core';

export type StreamEnd =
  | { kind: 'eof' } | { kind: 'aborted' } | { kind: 'http'; status: number } | { kind: 'error'; error: string };

export interface StreamTransport {
  (path: string, opts: { headers: Record<string, string>; signal: AbortSignal; onOpen: (status: number) => void; onChunk: (text: string) => void }): Promise<StreamEnd>;
}

export interface Clock {
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
  random(): number;
}

export const systemClock: Clock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: h => clearTimeout(h as ReturnType<typeof setTimeout>),
  random: () => Math.random(),
};

export interface EventStreamOptions {
  channels: readonly Channel[];
  jobId?: string | null;
  transport: StreamTransport;
  clock?: Clock;
  /** Extra headers (auth). When the platform cannot send headers, set useCursorParam. */
  headers?: () => Record<string, string>;
  useCursorParam?: boolean;
  initialCursor?: string | null;
  onEvent?: (env: Envelope) => void;
  onReset?: () => void;
  onLagged?: (dropped: number) => void;
  onState?: (state: StreamState) => void;
  /** Stop retrying on auth failures (401/403) — the session gate takes over. */
  fatalStatuses?: readonly number[];
}

export class EventStreamClient {
  private state: StreamState;
  private clock: Clock;
  private abort: AbortController | null = null;
  private watchdog: unknown = null;
  private retryTimer: unknown = null;
  private stopped = true;
  private generation = 0;

  constructor(private opts: EventStreamOptions) {
    this.clock = opts.clock ?? systemClock;
    this.state = initialStreamState(opts.initialCursor ?? null);
  }

  getState(): StreamState { return this.state; }

  start() {
    if (!this.stopped) return;
    this.stopped = false;
    this.connect();
  }

  stop() {
    this.stopped = true;
    this.generation += 1;
    this.clearTimers();
    this.abort?.abort();
    this.abort = null;
    this.set({ ...this.state, status: 'closed', connectedAt: null });
  }

  private set(next: StreamState) {
    this.state = next;
    try { this.opts.onState?.(next); } catch {}
  }

  private clearTimers() {
    if (this.watchdog !== null) { this.clock.clearTimeout(this.watchdog); this.watchdog = null; }
    if (this.retryTimer !== null) { this.clock.clearTimeout(this.retryTimer); this.retryTimer = null; }
  }

  private armWatchdog(gen: number) {
    if (this.watchdog !== null) this.clock.clearTimeout(this.watchdog);
    this.watchdog = this.clock.setTimeout(() => {
      this.watchdog = null;
      if (gen !== this.generation || this.stopped) return;
      if (isStreamDead(this.state.lastActivityAt, this.clock.now())) {
        this.abort?.abort(); // dead stream: the transport resolves 'aborted' → reconnect
      } else {
        this.armWatchdog(gen);
      }
    }, Math.max(1_000, LIVENESS_TIMEOUT_MS - (this.clock.now() - this.state.lastActivityAt)));
  }

  private connect() {
    if (this.stopped) return;
    const gen = ++this.generation;
    const abort = new AbortController();
    this.abort = abort;
    const parser = new SseParser();
    const cursor = this.state.cursor;
    const path = buildStreamPath({ channels: this.opts.channels, jobId: this.opts.jobId, cursor, useCursorParam: this.opts.useCursorParam });
    const headers = { ...(this.opts.headers?.() ?? {}), ...(this.opts.useCursorParam ? {} : resumeHeaders(cursor)) };
    this.set({ ...this.state, status: this.state.attempt > 0 ? 'reconnecting' : 'connecting', lastActivityAt: this.clock.now() });
    this.armWatchdog(gen);

    this.opts.transport(path, {
      headers,
      signal: abort.signal,
      onOpen: () => {
        if (gen !== this.generation) return;
        const now = this.clock.now();
        this.set({ ...this.state, status: 'open', connectedAt: now, lastActivityAt: now });
      },
      onChunk: text => {
        if (gen !== this.generation) return;
        for (const item of parser.feed(text)) {
          const { state, effects } = applyItem(this.state, item, this.clock.now());
          this.set(state);
          for (const e of effects) {
            try {
              if (e.kind === 'deliver') this.opts.onEvent?.(e.envelope);
              else if (e.kind === 'reset') this.opts.onReset?.();
              else this.opts.onLagged?.(e.dropped);
            } catch {}
          }
        }
      },
    }).then(end => this.onEnd(gen, end), () => this.onEnd(gen, { kind: 'error', error: 'transport_threw' }));
  }

  private onEnd(gen: number, end: StreamEnd) {
    if (gen !== this.generation || this.stopped) return;
    if (this.watchdog !== null) { this.clock.clearTimeout(this.watchdog); this.watchdog = null; }
    if (end.kind === 'http' && (this.opts.fatalStatuses ?? [401, 403]).includes(end.status)) {
      this.stopped = true;
      this.set({ ...this.state, status: 'closed', connectedAt: null });
      return;
    }
    const now = this.clock.now();
    const attempt = nextAttempt(this.state.attempt, this.state.connectedAt, now);
    const delay = backoffDelay(attempt - 1, () => this.clock.random(), this.state.retryFloorMs);
    this.set({ ...this.state, status: 'reconnecting', attempt, connectedAt: null });
    this.retryTimer = this.clock.setTimeout(() => { this.retryTimer = null; this.connect(); }, delay);
  }
}
