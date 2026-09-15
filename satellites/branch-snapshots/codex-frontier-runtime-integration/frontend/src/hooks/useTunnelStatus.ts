/**
 * src/hooks/useTunnelStatus.ts — React hook over the tunnel heartbeat.
 */
import { useEffect, useState } from 'react';
import {
  TunnelStatus, getTunnelStatus, getTunnelMeta, subscribeTunnel, startTunnelHeartbeat,
} from '../utils/tunnelHeartbeat';

export function useTunnelStatus(): { status: TunnelStatus; meta: any } {
  const [status, setStatus] = useState<TunnelStatus>(getTunnelStatus());
  const [meta, setMeta]     = useState<any>(getTunnelMeta());

  useEffect(() => {
    startTunnelHeartbeat();
    return subscribeTunnel((s, m) => { setStatus(s); setMeta(m); });
  }, []);

  return { status, meta };
}

export default useTunnelStatus;
