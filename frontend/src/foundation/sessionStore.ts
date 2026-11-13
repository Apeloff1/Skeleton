/**
 * App-wide session store (zustand) bridging the existing GameForge auth client
 * (`/api/auth/me` public contract) to the pure gating rules in sessionGate.ts.
 *
 * `checkMe` and `logout` are the session operations on src/utils/apiClient.ts,
 * the single TypeScript HTTP transport. This store does not call fetch itself.
 */
import { create } from 'zustand';
import { checkMe, logout } from '../auth/gameforgeAuth';
import { INITIAL_SESSION, SessionSnapshot, snapshotFromMe } from './sessionGate';
import { appQueryCache } from './queryCache';

interface SessionStore extends SessionSnapshot {
  user: unknown;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

let inflight: Promise<void> | null = null;

export const useSession = create<SessionStore>((set, get) => ({
  ...INITIAL_SESSION,
  user: null,
  refresh: () => {
    if (inflight) return inflight;
    if (get().status === 'unknown') set({ status: 'checking' });
    inflight = checkMe()
      .then(me => { set({ ...snapshotFromMe(me), user: me.authenticated ? me.user : null }); })
      .catch(err => {
        set({ status: 'unavailable', enforced: true, role: 'anonymous', user: null, error: err instanceof Error ? err.message : null });
      })
      .finally(() => { inflight = null; });
    return inflight;
  },
  signOut: async () => {
    try { await logout(); } finally {
      appQueryCache.clear();
      set({ status: 'anonymous', role: 'anonymous', user: null, error: null });
    }
  },
}));

export function selectSnapshot(s: SessionStore): SessionSnapshot {
  return { status: s.status, enforced: s.enforced, role: s.role, error: s.error };
}
