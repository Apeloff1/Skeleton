import { useCallback, useEffect, useRef, useState } from 'react';
import { getAuthToken } from '../auth/gameforgeAuth';
import { useStudioForeground } from '../features/Jeeves/useStudioForeground';
import { getChatReadiness, type ChatReadiness } from './chatSessionClient';

/** A current server observation, refreshed on return; it is never an execution grant. */
export function useChatReadiness(enabled = true) {
  const [readiness, setReadiness] = useState<ChatReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const active = useStudioForeground();
  const request = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const mounted = useRef(true);
  const refresh = useCallback(async (): Promise<void> => {
    if (!enabled || !mounted.current) return;
    const generation = ++epoch.current;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const token = getAuthToken();
    setBusy(true);
    try {
      const value = await getChatReadiness(controller.signal);
      if (mounted.current && !controller.signal.aborted && generation === epoch.current && token === getAuthToken()) {
        setReadiness(value);
        setObservedAt(new Date().toISOString());
      }
    } catch {
      if (mounted.current && !controller.signal.aborted && generation === epoch.current) {
        setReadiness(null);
        setObservedAt(null);
      }
    } finally {
      if (mounted.current && generation === epoch.current) setBusy(false);
    }
  }, [enabled]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; epoch.current += 1; request.current?.abort(); };
  }, []);
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
  return { readiness, busy, observedAt, refresh };
}
