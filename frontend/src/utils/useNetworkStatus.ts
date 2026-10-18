/**
 * Reachability observer for long-running mobile/web sessions.
 *
 * Probes never overlap, own a deadline spanning non-cooperative fetch shims,
 * and stop on unmount/background. A new foreground epoch fences old responses.
 * Native NetInfo and web connectivity events take priority when available.
 */
import { useEffect, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { API_BASE as CANONICAL_API_BASE } from './apiBase';
import { toast } from '../components/AppToast';

const BACKEND = CANONICAL_API_BASE;
const PROBE_MS = 15_000;
const PROBE_TIMEOUT_MS = 4_000;
export type NetType = 'wifi' | 'cellular' | 'ethernet' | 'other' | 'unknown' | 'none';
export interface NetworkStatus {
  online: boolean;
  type: NetType;
  isCellular: boolean;
  isWifi: boolean;
  lastChange: number;
}
let nativeNetInfo: null | { addEventListener?: (cb: (state: any) => void) => (() => void) } = null;
try {
  // Optional native dependency; fallback remains functional on web.
  nativeNetInfo = require('@react-native-community/netinfo').default;
} catch { /* optional */ }

export function useNetworkStatus(): NetworkStatus {
  const [status, setStatus] = useState<NetworkStatus>(() => ({
    online: true, type: 'unknown', isCellular: false, isWifi: false,
    lastChange: Date.now(),
  }));
  const latest = useRef(status);
  const everOffline = useRef(false);
  useEffect(() => {
    let disposed = false;
    let epoch = 0;
    let appState: AppStateStatus = AppState.currentState === 'background' ||
      AppState.currentState === 'inactive' ? AppState.currentState : 'active';
    let unsubscribe: (() => void) | null = null;
    let appSubscription: { remove: () => void } | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    let probing = false;

    const apply = (online: boolean, type: NetType = latest.current.type) => {
      if (disposed || (online === latest.current.online && type === latest.current.type)) return;
      const previous = latest.current.online;
      const next: NetworkStatus = {
        online, type, isCellular: type === 'cellular', isWifi: type === 'wifi',
        lastChange: Date.now(),
      };
      latest.current = next;
      setStatus(next);
      if (!online) {
        everOffline.current = true;
        if (previous) {
          try { toast.warn('Offline · retries paused'); } catch {}
        }
      } else if (!previous && everOffline.current) {
        try { toast.info('Online again', { durationMs: 1800 }); } catch {}
      }
    };
    const releaseProbe = () => {
      if (timer) clearTimeout(timer);
      timer = null;
      controller?.abort();
      controller = null;
      epoch++;
    };
    const schedule = (ms: number) => {
      if (disposed || appState !== 'active' || timer) return;
      timer = setTimeout(() => { timer = null; void probe(); }, ms);
    };
    const probe = async () => {
      if (disposed || appState !== 'active' || probing || !BACKEND) return;
      probing = true;
      const ownEpoch = epoch;
      const active = new AbortController();
      controller = active;
      let onTimeout: ReturnType<typeof setTimeout> | null = null;
      let abortReject = () => {};
      const aborted = new Promise<never>((_resolve, reject) => {
        abortReject = () => reject(new Error('Network probe aborted'));
        active.signal.addEventListener('abort', abortReject, { once: true });
      });
      onTimeout = setTimeout(() => active.abort(), PROBE_TIMEOUT_MS);
      try {
        const response = await Promise.race([
          fetch(BACKEND.replace(/\/+$/, '') + '/api/health', {
            signal: active.signal, method: 'GET',
            headers: { Accept: 'application/json', 'Cache-Control': 'no-store' },
          }),
          aborted,
        ]);
        if (!disposed && ownEpoch === epoch && appState === 'active') {
          apply(response.ok);
        }
      } catch {
        if (!disposed && ownEpoch === epoch && appState === 'active') apply(false);
      } finally {
        if (onTimeout) clearTimeout(onTimeout);
        active.signal.removeEventListener('abort', abortReject);
        if (controller === active) controller = null;
        probing = false;
        schedule(PROBE_MS);
      }
    };
    let hasConnectivitySource = false;
    if (nativeNetInfo && typeof nativeNetInfo.addEventListener === 'function') {
      try {
        const remove = nativeNetInfo.addEventListener(s => {
          if (disposed) return;
          const type = typeof s.type === 'string' &&
            ['wifi', 'cellular', 'ethernet', 'other', 'unknown', 'none'].includes(s.type)
            ? s.type as NetType : 'unknown';
          apply(s.isConnected === true && s.isInternetReachable !== false, type);
        });
        if (typeof remove === 'function') {
          unsubscribe = remove;
          hasConnectivitySource = true;
        }
      } catch { /* use fallback */ }
    }
    if (!hasConnectivitySource && typeof window !== 'undefined' &&
        typeof window.addEventListener === 'function') {
      const onOnline = () => apply(true);
      const onOffline = () => apply(false);
      window.addEventListener('online', onOnline);
      window.addEventListener('offline', onOffline);
      unsubscribe = () => {
        window.removeEventListener('online', onOnline);
        window.removeEventListener('offline', onOffline);
      };
      hasConnectivitySource = true;
      try { apply(navigator.onLine !== false); } catch {}
    }
    if (!hasConnectivitySource && BACKEND) {
      try {
        appSubscription = AppState.addEventListener('change', state => {
          appState = state;
          if (state === 'active') {
            releaseProbe();
            probing = false;
            schedule(0);
          } else {
            releaseProbe();
          }
        });
      } catch {}
      schedule(0);
    }
    return () => {
      disposed = true;
      releaseProbe();
      try { unsubscribe?.(); } catch {}
      appSubscription?.remove();
    };
  }, []);
  return status;
}
