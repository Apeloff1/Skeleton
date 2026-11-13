/**
 * Pure session-gating rules for the auth-gated route groups.
 *
 * Kept dependency-free so it runs under `node --test` without React Native.
 */
export type SessionStatus = 'unknown' | 'checking' | 'authenticated' | 'anonymous' | 'unavailable';

export interface SessionSnapshot {
  status: SessionStatus;
  /** Backend reports auth is enforced. When false, anonymous use is allowed. */
  enforced: boolean;
  role: string;
  error?: string | null;
}

export type GateDecision =
  | { kind: 'wait' }
  | { kind: 'allow' }
  | { kind: 'redirect'; to: string }
  | { kind: 'error'; message: string };

export const SIGN_IN_ROUTE = '/sign-in';
export const DEFAULT_SIGNED_IN_ROUTE = '/';

export const INITIAL_SESSION: SessionSnapshot = Object.freeze({
  status: 'unknown', enforced: true, role: 'anonymous', error: null,
}) as SessionSnapshot;

/** Only allow app-internal return paths (no protocol, no protocol-relative). */
export function safeReturnTo(value: unknown, fallback: string = DEFAULT_SIGNED_IN_ROUTE): string {
  if (typeof value !== 'string') return fallback;
  const trimmed = value.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//') || trimmed.includes('://') || trimmed.includes('\\')) {
    return fallback;
  }
  if (trimmed === SIGN_IN_ROUTE || trimmed.startsWith(SIGN_IN_ROUTE + '?')) return fallback;
  return trimmed;
}

export function signInHref(returnTo: string): string {
  return `${SIGN_IN_ROUTE}?returnTo=${encodeURIComponent(safeReturnTo(returnTo))}`;
}

/** Decide what a gated layout renders for the current session. */
export function decideGate(
  session: SessionSnapshot,
  pathname: string,
  opts: { requiredRole?: string } = {},
): GateDecision {
  switch (session.status) {
    case 'unknown':
    case 'checking':
      return { kind: 'wait' };
    case 'unavailable':
      return { kind: 'error', message: session.error || 'The sign-in service is unavailable.' };
    case 'anonymous':
      if (!session.enforced && !opts.requiredRole) return { kind: 'allow' };
      return { kind: 'redirect', to: signInHref(pathname) };
    case 'authenticated':
      if (opts.requiredRole && !roleSatisfies(session.role, opts.requiredRole)) {
        return { kind: 'error', message: 'Your account does not have access to this area.' };
      }
      return { kind: 'allow' };
    default:
      return { kind: 'wait' };
  }
}

const ROLE_RANK: Record<string, number> = { anonymous: 0, viewer: 1, user: 2, creator: 3, admin: 4, owner: 5 };

export function roleSatisfies(role: string, required: string): boolean {
  const have = ROLE_RANK[role] ?? (role === required ? Number.POSITIVE_INFINITY : 0);
  const need = ROLE_RANK[required] ?? Number.POSITIVE_INFINITY;
  return role === required || have >= need;
}

/** Map the backend `/api/auth/me` result (public contract) onto a snapshot. */
export function snapshotFromMe(me: {
  authenticated: boolean; enforced: boolean; role?: string; observed?: boolean; error?: string;
}): SessionSnapshot {
  if (me.observed === false) {
    return { status: 'unavailable', enforced: true, role: 'anonymous', error: me.error || null };
  }
  return {
    status: me.authenticated ? 'authenticated' : 'anonymous',
    enforced: me.enforced,
    role: me.authenticated ? me.role || 'user' : 'anonymous',
    error: null,
  };
}
