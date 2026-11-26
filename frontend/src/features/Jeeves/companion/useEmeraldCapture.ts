import { useEffect, useState } from 'react';
import type { CapturedSource, CrawlEvent, CrawlSession } from '../../../product/crawlerClient';
import { initialEmerald, projectEmerald } from './emeraldCapture';

export function useEmeraldCapture(session: CrawlSession | null, events: readonly CrawlEvent[],
  sources: readonly CapturedSource[], observed: boolean, stale: boolean) {
  const [projection,setProjection] = useState(() => initialEmerald(''));
  useEffect(() => {
    setProjection(previous => session ? projectEmerald(previous,session,events,sources,observed,stale) : initialEmerald(''));
  },[session,events,sources,observed,stale]);
  if (!session || projection.sessionId !== session.session_id) return initialEmerald(session?.session_id ?? '');
  return stale || !observed ? {...projection, cue:null, target:null, availability:'stale' as const} : projection;
}
