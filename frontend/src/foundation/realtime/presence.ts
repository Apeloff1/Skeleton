/**
 * Presence over `POST /api/v1/presence` ({action, scope, client_id}).
 * Pure helpers + a scheduler with injected transport/clock for tests.
 */
export type PresenceAction = 'join' | 'heartbeat' | 'leave';
export interface PresenceBody { action: PresenceAction; scope: string; client_id: string; meta?: Record<string, unknown> }
export const PRESENCE_PATH = '/api/v1/presence';
/** Server expires a member after 45s of silence; the SDK heartbeats every 15s. */
export const PRESENCE_HEARTBEAT_MS = 15_000;

export function presenceBody(action: PresenceAction, scope: string, clientId: string, meta?: Record<string, unknown>): PresenceBody {
  if (!scope || !clientId) throw new Error('presence requires scope and client_id');
  const body: PresenceBody = { action, scope, client_id: clientId };
  if (action === 'join' && meta && Object.keys(meta).length) body.meta = meta;
  return body;
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
export function startPresence(scope: string, clientId: string, deps: PresenceDeps, intervalMs = PRESENCE_HEARTBEAT_MS, meta?: Record<string, unknown>): () => void {
  const send = (a: PresenceAction) => { void Promise.resolve().then(() => deps.post(PRESENCE_PATH, presenceBody(a, scope, clientId, meta))).catch(() => {}); };
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
