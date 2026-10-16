/**
 * src/hooks/useTunnelStatus.ts — React hook over the tunnel heartbeat.
 */
import { useEffect, useState } from 'react';
import {
  TunnelStatus, getTunnelStatus, getTunnelMeta, subscribeTunnel,
} from '../utils/tunnelHeartbeat';

export function useTunnelStatus(): { status: TunnelStatus; meta: any } {
  const [status, setStatus] = useState<TunnelStatus>(getTunnelStatus());
  const [meta, setMeta]     = useState<any>(getTunnelMeta());

  useEffect(() => {
    // The root layout owns delayed heartbeat activation, not a visual banner.
    return subscribeTunnel((s, m) => { setStatus(s); setMeta(m); });
  }, []);

  return { status, meta };
}

export default useTunnelStatus;
