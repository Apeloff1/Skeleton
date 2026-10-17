/**
 * React bindings for the canonical realtime stream (ADR-realtime-transport v1).
 * - `useEventStream`: subscribe to channels, get status + last events.
 * - On `stream.reset` the foundation query cache is invalidated so screens
 *   refetch over REST; `stream.lagged` is surfaced as a notice.
 * - `usePresence`: join/heartbeat/leave via POST /api/v1/presence.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import api, { openEventStream } from '../../utils/apiClient';
import { authHeaders } from '../../auth/gameforgeAuth';
import { appQueryCache, QueryKey } from '../queryCache';
import type { Channel, Envelope, StreamStatus } from './core';
import { EventStreamClient } from './client';
import { newClientId, startPresence } from './presence';

export interface UseEventStreamOptions {
  channels: readonly Channel[];
  jobId?: string | null;
  enabled?: boolean;
  onEvent?: (env: Envelope) => void;
  /** Query keys (prefixes) to invalidate on stream.reset; default: whole cache. */
  invalidateOnReset?: readonly QueryKey[];
}

export interface EventStreamView {
  status: StreamStatus;
  connected: boolean;
  lastEvent: Envelope | null;
  laggedNotice: number | null;
  dismissLagged: () => void;
}

export function useEventStream(opts: UseEventStreamOptions): EventStreamView {
  const { channels, jobId = null, enabled = true } = opts;
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [lastEvent, setLastEvent] = useState<Envelope | null>(null);
  const [laggedNotice, setLagged] = useState<number | null>(null);
  const ref = useRef(opts);
  ref.current = opts;
  const channelKey = [...channels].sort().join(',');

  useEffect(() => {
    if (!enabled) return;
    const client = new EventStreamClient({
      channels: channelKey.split(',') as Channel[],
      jobId,
      headers: () => authHeaders(),
      transport: (path, t) => openEventStream(path, t),
      onState: s => setStatus(s.status),
      onEvent: env => { setLastEvent(env); try { ref.current.onEvent?.(env); } catch {} },
      onReset: () => {
        const keys = ref.current.invalidateOnReset;
        if (keys && keys.length) keys.forEach(k => appQueryCache.invalidate(k));
        else appQueryCache.invalidate();
      },
      onLagged: dropped => setLagged(dropped),
    });
    client.start();
    return () => client.stop();
  }, [enabled, channelKey, jobId]);

  return { status, connected: status === 'open', lastEvent, laggedNotice, dismissLagged: () => setLagged(null) };
}

export function usePresence(scope: string | null, enabled = true) {
  const clientId = useMemo(() => newClientId(), []);
  useEffect(() => {
    if (!enabled || !scope) return;
    return startPresence(scope, clientId, {
      post: (path, body) => api.post(path, body, { headers: authHeaders(), retries: 0, timeoutMs: 10_000 }),
      setInterval: (fn, ms) => setInterval(fn, ms),
      clearInterval: h => clearInterval(h as ReturnType<typeof setInterval>),
    });
  }, [scope, enabled, clientId]);
  return clientId;
}
