/**
 * useNetworkStatus — online/offline + connection-type awareness.
 *
 * Returns:
 *   { online, type, isCellular, isWifi, lastChange }
 *
 * Strategy:
 *   • Tries to use @react-native-community/netinfo if installed.
 *   • Falls back to a fetch-probe heartbeat against EXPO_PUBLIC_BACKEND_URL
 *     every 15s so the hook works even without netinfo.
 *   • On web, uses `navigator.onLine` + 'online'/'offline' listeners.
 *
 * 2026-02 — Also surfaces a single toast on the
 *   online → offline (toast.warn 'Offline') and
 *   offline → online (toast.info 'Online again')
 * transitions, so users have a clear non-blocking confirmation that
 * the network came back without watching the OfflineBanner disappear.
 */
import { useEffect, useRef, useState } from 'react';
import { toast } from '../components/Toast';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export type NetType = 'wifi' | 'cellular' | 'ethernet' | 'other' | 'unknown' | 'none';

export interface NetworkStatus {
  online:     boolean;
  type:       NetType;
  isCellular: boolean;
  isWifi:     boolean;
  lastChange: number;
}

let _netinfo: any = null;
try { _netinfo = require('@react-native-community/netinfo').default; } catch { /* not installed — that's fine */ }

export function useNetworkStatus(): NetworkStatus {
  const [status, setStatus] = useState<NetworkStatus>(() => ({
    online: true, type: 'unknown', isCellular: false, isWifi: false, lastChange: Date.now(),
  }));
  const last = useRef<NetworkStatus>(status);
  /** Track whether we've ever observed an offline state — used to avoid
   *  firing a misleading "Online again" toast on the very first mount
   *  when we transition from the optimistic `online: true` default to
   *  netinfo's first emission. */
  const everOffline = useRef<boolean>(false);

  const _applyAndNotify = (next: NetworkStatus) => {
    const wasOnline = last.current.online;
    last.current = next;
    setStatus(next);
    if (!next.online) {
      // Only show the offline toast on a real online → offline transition.
      if (wasOnline) {
        everOffline.current = true;
        try { toast.warn('Offline · retries paused'); } catch { /* swallow */ }
      } else {
        everOffline.current = true;
      }
    } else if (wasOnline === false && everOffline.current) {
      // Genuine offline → online recovery.
      try { toast.info('Online again', { durationMs: 1800 }); } catch { /* swallow */ }
    }
  };

  useEffect(() => {
    let unsub: (() => void) | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;

    // ── netinfo path ─────────────────────────────────────────────
    if (_netinfo && typeof _netinfo.addEventListener === 'function') {
      try {
        unsub = _netinfo.addEventListener((s: any) => {
          const next: NetworkStatus = {
            online:     !!s.isConnected && s.isInternetReachable !== false,
            type:       (s.type as NetType) || 'unknown',
            isCellular: s.type === 'cellular',
            isWifi:     s.type === 'wifi',
            lastChange: Date.now(),
          };
          if (next.online !== last.current.online || next.type !== last.current.type) {
            _applyAndNotify(next);
          }
        });
      } catch { /* fall through */ }
    }

    // ── Web 'online'/'offline' events ────────────────────────────
    if (!unsub && typeof window !== 'undefined' && 'addEventListener' in window) {
      const onOnline  = () => { _applyAndNotify({ ...last.current, online: true,  lastChange: Date.now() }); };
      const onOffline = () => { _applyAndNotify({ ...last.current, online: false, lastChange: Date.now() }); };
      window.addEventListener('online',  onOnline);
      window.addEventListener('offline', onOffline);
      unsub = () => {
        window.removeEventListener('online',  onOnline);
        window.removeEventListener('offline', onOffline);
      };
      // Initial probe.
      try {
        const online = (navigator as any).onLine !== false;
        if (online !== last.current.online) { _applyAndNotify({ ...last.current, online, lastChange: Date.now() }); }
      } catch { /* swallow */ }
    }

    // ── Heartbeat fallback ───────────────────────────────────────
    if (!unsub && BACKEND) {
      const probe = async () => {
        try {
          const ctrl = new AbortController();
          const t = setTimeout(() => ctrl.abort(), 4000);
          const res = await fetch(`${BACKEND}/api/health`, { signal: ctrl.signal });
          clearTimeout(t);
          const online = res.ok;
          if (online !== last.current.online) {
            _applyAndNotify({ ...last.current, online, lastChange: Date.now() });
          }
        } catch {
          if (last.current.online) {
            _applyAndNotify({ ...last.current, online: false, lastChange: Date.now() });
          }
        }
      };
      probe();
      timer = setInterval(probe, 15000);
      unsub = () => { if (timer) clearInterval(timer); };
    }

    return () => { try { unsub?.(); } catch { /* swallow */ } };
  }, []);

  return status;
}
