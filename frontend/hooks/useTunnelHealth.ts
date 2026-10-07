/**
 * useTunnelHealth — subscribe to the ngrok/tunnel health observable
 * exposed by `utils/resilientNet`. Lets any component reactively render
 * whether the backend is healthy, degraded, or offline.
 */
import { useEffect, useState } from 'react';
import {
  subscribeTunnelHealth,
  startHeartbeat,
  getTunnelHealth,
  type TunnelStatus,
} from '../utils/resilientNet';

export interface TunnelHealth {
  status: TunnelStatus;
  lastOkTs: number;
  lastFailTs: number;
  consecutiveFailures: number;
  circuitOpen: boolean;
  circuitOpenUntil: number;
  rttMs: number;
  ageMs: number;
}

export function useTunnelHealth(): TunnelHealth {
  const [state, setState] = useState(() => getTunnelHealth());

  useEffect(() => {
    // Ensure heartbeat is running (idempotent)
    startHeartbeat();
    const unsub = subscribeTunnelHealth((s) => setState({ ...s }));
    return () => { unsub(); };
  }, []);

  return {
    ...state,
    ageMs: state.lastOkTs ? Date.now() - state.lastOkTs : Infinity,
  };
}

export default useTunnelHealth;
