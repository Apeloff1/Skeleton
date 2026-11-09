/**
 * Live-Ops helpers shared across screens.
 *  - getVisitorId(): stable, locally-stored anonymous id (also used by marketplace).
 *  - awardXp(action): fire-and-forget XP grant for an engagement action. XP is
 *    server-authoritative (the backend decides the amount + any event multiplier);
 *    the client only names the action. Failures are swallowed silently.
 */
import api from './apiClient';
import { safeGetItem, safeSetItem } from '../../utils/safeStorage';

const VISITOR_KEY = 'mkt_visitor_id';

export async function getVisitorId(): Promise<string> {
  let id = await safeGetItem(VISITOR_KEY);
  if (!id) {
    id = 'v_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    await safeSetItem(VISITOR_KEY, id);
  }
  return id;
}

export type XpAction = 'play' | 'vote' | 'react' | 'generate' | 'remix' | 'purchase' | 'share';

export async function awardXp(action: XpAction): Promise<void> {
  try {
    const visitor_id = await getVisitorId();
    await api.post('/api/liveops/xp', { visitor_id, action }, { timeoutMs: 8000, retries: 0 });
  } catch {
    /* best-effort: Live-Ops XP is non-critical */
  }
}
