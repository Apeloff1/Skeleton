/**
 * Presence over `POST /api/v1/presence` ({action, scope, client_id}).
 * Pure helpers + a scheduler with injected transport/clock for tests.
 */
export type PresenceAction = 'join' | 'heartbeat' | 'leave';
export interface PresenceBody { action: PresenceAction; scope: string; client_id: string }
export const PRESENCE_PATH = '/api/v1/presence';
export const PRESENCE_HEARTBEAT_MS = 30_000;

export function presenceBody(action: PresenceAction, scope: string, clientId: string): PresenceBody {
  if (!scope || !clientId) throw new Error('presence requires scope and client_id');
  return { action, scope, client_id: clientId };
}

export function newClientId(random: () => number = Math.random): string {
  let s = '';
  for (let i = 0; i < 16; i++) s += Math.floor(random() * 16).toString(16);
  return `c_${s}`;
}

export interface PresenceDeps {
  post: (path: string, body: PresenceBody) => Promise<unknown>;
  setInterval: (fn: () => void, ms: number) => unknown;
  clearInterval: (h: unknown) => void;
}

/** Join now, heartbeat on an interval, leave on dispose. Errors never throw to the UI. */
export function startPresence(scope: string, clientId: string, deps: PresenceDeps, intervalMs = PRESENCE_HEARTBEAT_MS): () => void {
  const send = (a: PresenceAction) => { void Promise.resolve().then(() => deps.post(PRESENCE_PATH, presenceBody(a, scope, clientId))).catch(() => {}); };
  send('join');
  const h = deps.setInterval(() => send('heartbeat'), intervalMs);
  let done = false;
  return () => {
    if (done) return;
    done = true;
    deps.clearInterval(h);
    send('leave');
  };
}
