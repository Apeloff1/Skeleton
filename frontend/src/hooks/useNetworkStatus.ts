/**
 * src/hooks/useNetworkStatus.ts — hook reporting online/offline state.
 *
 * Uses @react-native-community/netinfo when available, falls back to the
 * web `navigator.onLine` API. Subscribes on mount and cleans up on unmount.
 */
import React from 'react';
import { Platform } from 'react-native';

export type NetStatus = 'online' | 'offline' | 'unknown';

export function useNetworkStatus(): NetStatus {
  const [status, setStatus] = React.useState<NetStatus>('unknown');

  React.useEffect(() => {
    let cancelled = false;
    if (Platform.OS === 'web') {
      const update = () => !cancelled && setStatus(navigator.onLine ? 'online' : 'offline');
      update();
      window.addEventListener('online',  update);
      window.addEventListener('offline', update);
      return () => {
        cancelled = true;
        window.removeEventListener('online',  update);
        window.removeEventListener('offline', update);
      };
    } else {
      let unsub: any = null;
      (async () => {
        try {
          const NetInfo: any = await import('@react-native-community/netinfo');
          // Dynamic import can settle after unmount; never install an orphan
          // OS network listener once the component has gone away.
          if (cancelled) return;
          unsub = NetInfo.default.addEventListener((state: any) => {
            if (!cancelled) setStatus(state.isConnected ? 'online' : 'offline');
          });
          if (cancelled) { try { unsub?.(); } catch {} }
        } catch {
          if (!cancelled) setStatus('unknown');
        }
      })();
      return () => { cancelled = true; try { unsub?.(); } catch {} };
    }
  }, []);

  return status;
}

export default useNetworkStatus;
