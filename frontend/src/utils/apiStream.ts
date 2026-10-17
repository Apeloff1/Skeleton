/**
 * Streaming companion to apiClient.ts (same API_BASE, same auth contract).
 * Long-lived SSE reads live here so apiClient's request/retry/circuit-breaker
 * path stays request/response only. Consumed by src/foundation/realtime.
 */
import { API_BASE } from './apiBase';
const BACKEND = API_BASE;
// ── Streaming transport (SSE, ADR-realtime-transport v1) ─────────────────
// The one place the app opens a long-lived HTTP stream. Uses the platform
// fetch when it exposes a readable body (web), and Expo's streaming fetch on
// native. Callers (src/foundation/realtime) own parsing, resume and backoff.
export interface EventStreamOpts {
  headers?: Record<string, string>;
  signal?: AbortSignal;
  onOpen?: (status: number) => void;
  onChunk: (text: string) => void;
}
export type EventStreamEnd =
  | { kind: 'eof' } | { kind: 'aborted' } | { kind: 'http'; status: number } | { kind: 'error'; error: string };

type StreamFetch = (url: string, init: { headers: Record<string, string>; signal?: AbortSignal }) => Promise<{
  ok: boolean; status: number;
  body?: { getReader?: () => { read: () => Promise<{ done: boolean; value?: Uint8Array }>; cancel?: () => Promise<void> } } | null;
  text: () => Promise<string>;
}>;

function resolveStreamFetch(): StreamFetch {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const expoFetch = require('expo/fetch')?.fetch;
    if (typeof expoFetch === 'function') return expoFetch as StreamFetch;
  } catch {}
  return fetch as unknown as StreamFetch;
}

export async function openEventStream(path: string, opts: EventStreamOpts): Promise<EventStreamEnd> {
  const url = /^https?:\/\//i.test(path) ? path : `${BACKEND}${path}`;
  try {
    const res = await resolveStreamFetch()(url, {
      headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache', ...opts.headers },
      signal: opts.signal,
    });
    if (!res.ok) return { kind: 'http', status: res.status };
    opts.onOpen?.(res.status);
    const reader = res.body?.getReader?.();
    if (!reader) {
      // No streaming body on this platform: deliver what arrived; caller reconnects.
      opts.onChunk(await res.text());
      return { kind: 'eof' };
    }
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) opts.onChunk(decoder.decode(value, { stream: true }));
    }
    const tail = decoder.decode();
    if (tail) opts.onChunk(tail);
    return { kind: 'eof' };
  } catch {
    if (opts.signal?.aborted) return { kind: 'aborted' };
    // Never surface raw exception text: it may echo signed URLs or headers.
    return { kind: 'error', error: 'network_error' };
  }
}
