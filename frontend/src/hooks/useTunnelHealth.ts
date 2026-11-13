/**
 * useTunnelHealth — subscribe to the ngrok/tunnel health observable
 * exposed by `utils/resilientNet`. Lets any component reactively render
 * whether the backend is healthy, degraded, or offline.
 */
import { useEffect, useState } from 'react';
import {
  subscribeTunnelHealth,
  retainHeartbeat,
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
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const releaseHeartbeat = retainHeartbeat();
    const unsub = subscribeTunnelHealth((s) => setState({ ...s }));
    // Age progresses even when no health transition produces a new event.
    const ticker = setInterval(() => setNow(Date.now()), 30_000);
    return () => {
      clearInterval(ticker);
      unsub();
      releaseHeartbeat();
    };
  }, []);

  return {
    ...state,
    ageMs: state.lastOkTs ? Math.max(0, now - state.lastOkTs) : Infinity,
  };
}

export default useTunnelHealth;
