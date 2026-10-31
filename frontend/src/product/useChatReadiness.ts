import { useCallback, useEffect, useRef, useState } from 'react';
import { getAuthToken } from '../auth/gameforgeAuth';
import { useStudioForeground } from '../features/Jeeves/useStudioForeground';
import { getChatReadiness, type ChatReadiness } from './chatSessionClient';
import { asChatError, ChatClientError } from './chatErrors';

/** A current server observation, refreshed on return; it is never an execution grant. */
export function useChatReadiness(enabled = true) {
  const [readiness, setReadiness] = useState<ChatReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const [error, setError] = useState<ChatClientError | null>(null);
  const active = useStudioForeground();
  const activeRef = useRef(active);
  activeRef.current = active;
  const accountToken = useRef(getAuthToken());
  const observedToken = useRef<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const mounted = useRef(true);
  const refresh = useCallback(async (): Promise<void> => {
    if (!enabled || !mounted.current || !activeRef.current) return;
    const generation = ++epoch.current;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const token = getAuthToken();
    if (accountToken.current !== token) {
      accountToken.current = token; observedToken.current = null;
      setReadiness(null); setObservedAt(null);
    }
    setBusy(true); setError(null);
    try {
      const value = await getChatReadiness(controller.signal);
      if (mounted.current && !controller.signal.aborted && generation === epoch.current && token === getAuthToken()) {
        setReadiness(value);
        setObservedAt(new Date().toISOString());
        observedToken.current = token;
      }
    } catch (cause) {
      if (mounted.current && !controller.signal.aborted && generation === epoch.current) {
        setReadiness(null);
        setObservedAt(null);
        observedToken.current = null;
        setError(asChatError(cause, 'AI readiness could not be observed. Check the engine connection and refresh.'));
      }
    } finally {
      if (mounted.current && generation === epoch.current) setBusy(false);
    }
  }, [enabled]);

  useEffect(() => {
    mounted.current = true;
    const timer = enabled ? setInterval(() => {
      if (accountToken.current === getAuthToken()) return;
      accountToken.current = getAuthToken(); observedToken.current = null;
      epoch.current += 1; request.current?.abort();
      setReadiness(null); setObservedAt(null); setBusy(false);
      setError(new ChatClientError('Your account changed. Refresh readiness for the current account.', { kind: 'authorization', retryable: false }));
      if (enabled && activeRef.current) void refresh();
    }, 1000) : null;
    return () => { mounted.current = false; if (timer !== null) clearInterval(timer); epoch.current += 1; request.current?.abort(); };
  }, [enabled, refresh]);
  useEffect(() => {
    if (!enabled || !active) { request.current?.abort(); setBusy(false); return; }
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 60000);
    const online = () => { void refresh(); };
    if (typeof window !== 'undefined') window.addEventListener('online', online);
    return () => {
      clearInterval(timer);
      request.current?.abort();
      if (typeof window !== 'undefined') window.removeEventListener('online', online);
    };
  }, [enabled, active, refresh]);
  const current = active && observedToken.current === getAuthToken();
  return { readiness: current ? readiness : null, busy, observedAt: current ? observedAt : null, error, refresh };
}
