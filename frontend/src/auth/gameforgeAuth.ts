/**
 * src/auth/gameforgeAuth.ts — GameForge Studio auth (Email/JWT + Emergent Google).
 *
 * Token storage: expo-secure-store on native, localStorage on web (never
 * AsyncStorage — unencrypted). The bearer token is either a JWT (email/password
 * login) or an opaque Google session token; the backend accepts both.
 */
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import api from '../utils/apiClient';

const KEY = 'gameforge_auth_token';
const EMERGENT_AUTH = 'https://auth.emergentagent.com/';

let _token = '';
let _tokenLoaded = false;
let _tokenEpoch = 0;
const _authObservers = new Set<() => void>();
let _tokenInitialization: Promise<void> | null = null;
let _tenantIdentityCache: {
  token: string;
  identity: { tenantId: string; principalId: string };
} | null = null;

export function getAuthToken(): string {
  return _token;
}

export function getAuthEpoch(): number { return _tokenEpoch; }

/** Invalidate observations without publishing bearer material. */
export function subscribeAuthChanges(observer: () => void): () => void {
  _authObservers.add(observer);
  return () => { _authObservers.delete(observer); };
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return _token ? { Authorization: `Bearer ${_token}`, ...extra } : { ...extra };
}

async function persist(token: string) {
  _tokenEpoch += 1;
  _tokenLoaded = true;
  if (token !== _token) _tenantIdentityCache = null;
  _token = token;
  for (const observer of _authObservers) { try { observer(); } catch {} }
  try {
    if (Platform.OS === 'web') {
      if (token) localStorage.setItem(KEY, token);
      else localStorage.removeItem(KEY);
    } else if (token) {
      await SecureStore.setItemAsync(KEY, token);
    } else {
      await SecureStore.deleteItemAsync(KEY);
    }
  } catch {}
}

/** Scoped bearer snapshot for raw private media.
 * A logout or account change invalidates the session before data is consumed.
 */
export async function prepareApiRequest(
  _url: string,
  extra: Record<string, string> = {},
  upstream?: AbortSignal,
): Promise<{ headers: Record<string, string>; signal: AbortSignal; current: () => boolean; dispose: () => void }> {
  await initializeStoredToken();
  const epoch = _tokenEpoch;
  const token = _token;
  const controller = new AbortController();
  const invalidate = () => { controller.abort(); };
  const unsubscribe = subscribeAuthChanges(invalidate);
  upstream?.addEventListener('abort', invalidate, { once: true });
  if (upstream?.aborted || epoch !== _tokenEpoch || token !== _token) invalidate();
  return {
    headers: { ...extra, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    signal: controller.signal,
    current: () => !controller.signal.aborted && epoch === _tokenEpoch && token === _token,
    dispose: () => {
      unsubscribe();
      upstream?.removeEventListener('abort', invalidate);
      controller.abort();
    },
  };
}

async function loadStored(): Promise<string> {
  try {
    if (Platform.OS === 'web') return localStorage.getItem(KEY) || '';
    return (await SecureStore.getItemAsync(KEY)) || '';
  } catch {
    return '';
  }
}

/** Share cold storage initialization without confusing it with an account change. */
async function initializeStoredToken(): Promise<void> {
  if (_tokenLoaded) return;
  if (!_tokenInitialization) {
    const epoch = _tokenEpoch;
    _tokenInitialization = loadStored().then((stored) => {
      if (_tokenEpoch !== epoch) throw new Error('Your account changed while loading storage.');
      _token = stored;
      _tokenLoaded = true;
    });
  }
  const initialization = _tokenInitialization;
  try {
    await initialization;
  } finally {
    if (_tokenInitialization === initialization) _tokenInitialization = null;
  }
}

export interface MeResult {
  authenticated: boolean;
  enforced: boolean;
  role: string;
  user: any;
  observed?: boolean;
  error?: string;
}

export type StorageTenantIdentity = {
  tenantId: string;
  principalId: string;
};

function storageIdentityFromUser(user: any): StorageTenantIdentity {
  const tenantId = String(
    user?.tenant_id || user?.email || '',
  ).trim();
  const principalId = String(
    user?.email || user?.tenant_id || '',
  ).trim();
  if (!tenantId || !principalId) {
    throw new Error('Authenticated tenant identity is unavailable.');
  }
  return { tenantId, principalId };
}

/**
 * Resolve the same tenant identity used by backend operation authorization.
 * Network/auth ambiguity fails closed; it never falls back into anonymous
 * storage merely because /auth/me was unreachable.
 */
export async function resolveStorageTenantIdentity(): Promise<StorageTenantIdentity> {
  const epoch = _tokenEpoch;
  await initializeStoredToken();
  if (_tokenEpoch !== epoch) throw new Error('Your account changed while resolving storage.');
  const stored = _token;

  if (
    _tenantIdentityCache
    && _tenantIdentityCache.token === stored
  ) {
    return _tenantIdentityCache.identity;
  }

  const r = await api.get<any>(
    '/api/auth/me',
    stored ? { headers: authHeaders() } : {},
  );
  if (_tokenEpoch !== epoch || _token !== stored) throw new Error('Your account changed while verifying storage.');
  if (r.status === 401) {
    await persist('');
    throw new Error('Tenant identity is no longer authenticated.');
  }
  if (!r.ok || !r.data || typeof r.data.authenticated !== 'boolean' || typeof r.data.enforced !== 'boolean') {
    throw new Error('Tenant identity could not be verified.');
  }

  const authenticated = Boolean(r.data.authenticated);
  const enforced = Boolean(r.data.enforced);
  let identity: StorageTenantIdentity;
  if (authenticated) {
    identity = storageIdentityFromUser(r.data.user);
  } else if (!enforced) {
    identity = {
      tenantId: 'anonymous',
      principalId: 'anonymous',
    };
  } else {
    throw new Error('Authenticated tenant identity is required.');
  }

  _tenantIdentityCache = {
    token: stored,
    identity,
  };
  return identity;
}

/** Validate the current token against the backend. Clears it on 401. */
export async function checkMe(signal?: AbortSignal): Promise<MeResult> {
  const unknown = (error: string): MeResult => ({ authenticated: false, enforced: true, role: 'anonymous', user: null, observed: false, error });
  const epoch = _tokenEpoch;
  try {
    await initializeStoredToken();
  } catch {
    return unknown('Your account changed. Verify the current session again.');
  }
  if (_tokenEpoch !== epoch) return unknown('Your account changed. Verify the current session again.');
  const stored = _token;
  if (signal?.aborted) return unknown('Account inspection cancelled.');
  const r = await api.get<any>('/api/auth/me', { signal, headers: authHeaders(), timeoutMs: 12000, retries: 0 });
  if (signal?.aborted) return unknown('Account inspection cancelled.');
  if (_tokenEpoch !== epoch || _token !== stored) return unknown('Your account changed. Verify the current session again.');
  if (r.status === 401) {
    await persist('');
    return { authenticated: false, enforced: true, role: 'anonymous', user: null, observed: true };
  }
  if (!r.ok || !r.data || typeof r.data.authenticated !== 'boolean' || typeof r.data.enforced !== 'boolean') {
    return unknown('The sign-in service could not be verified. Check application readiness and retry.');
  }
  const authed = r.data.authenticated;
  if (authed) {
    try {
      _tenantIdentityCache = { token: stored, identity: storageIdentityFromUser(r.data.user) };
    } catch {
      _tenantIdentityCache = null;
      return unknown('The account service returned an incomplete identity. Sign in again or check setup.');
    }
  } else if (!r.data.enforced) {
    _tenantIdentityCache = { token: stored, identity: { tenantId: 'anonymous', principalId: 'anonymous' } };
  } else {
    _tenantIdentityCache = null;
  }
  return { authenticated: authed, enforced: r.data.enforced, role: authed ? r.data.user?.role || 'anonymous' : 'anonymous', user: authed ? r.data.user : null, observed: true };
}

/** Email + password login (JWT). */
export async function loginEmail(email: string, password: string): Promise<{ ok: boolean; role?: string; error?: string }> {
  const r = await api.post<any>('/api/auth/login', { email: email.trim().toLowerCase(), password }, { timeoutMs: 15000 });
  if (r.ok && r.data?.access_token) {
    await persist(r.data.access_token);
    return { ok: true, role: r.data.role };
  }
  return { ok: false, error: r.data?.detail || 'Invalid credentials' };
}

/** Register a new viewer account (JWT). */
export async function registerEmail(email: string, password: string): Promise<{ ok: boolean; role?: string; error?: string }> {
  const r = await api.post<any>('/api/auth/register', { email: email.trim().toLowerCase(), password }, { timeoutMs: 15000 });
  if (r.ok && r.data?.access_token) {
    await persist(r.data.access_token);
    return { ok: true, role: r.data.role };
  }
  return { ok: false, error: r.data?.detail || 'Registration failed' };
}

function parseSessionId(url: string): string {
  if (!url) return '';
  const frag = url.includes('#') ? url.split('#')[1] : '';
  const query = url.includes('?') ? url.split('?')[1].split('#')[0] : '';
  for (const part of [frag, query]) {
    const m = /(?:^|&)session_id=([^&]+)/.exec(part || '');
    if (m) return decodeURIComponent(m[1]);
  }
  return '';
}

/** Exchange an Emergent session_id for a persistent token via the backend. */
async function exchangeSession(sessionId: string): Promise<{ ok: boolean; role?: string; error?: string }> {
  const r = await api.post<any>('/api/auth/session', { session_id: sessionId }, { timeoutMs: 20000 });
  if (r.ok && r.data?.access_token) {
    await persist(r.data.access_token);
    return { ok: true, role: r.data.role };
  }
  return { ok: false, error: r.data?.detail || 'Google sign-in failed' };
}

/**
 * On web, the Emergent redirect returns to the current route with
 * `#session_id=...`. Call this on mount to complete any pending web login.
 */
export async function completeWebRedirect(): Promise<{ ok: boolean; role?: string } | null> {
  if (Platform.OS !== 'web') return null;
  try {
    const sid = parseSessionId(window.location.hash) || parseSessionId(window.location.search);
    if (!sid) return null;
    const res = await exchangeSession(sid);
    // Clean the fragment so a refresh doesn't re-process a spent session_id.
    window.history.replaceState(null, '', window.location.pathname);
    return res.ok ? { ok: true, role: res.role } : { ok: false };
  } catch {
    return null;
  }
}

/** Kick off Emergent Google auth. Web navigates away; native opens a session. */
export async function googleLogin(): Promise<{ ok: boolean; role?: string; error?: string; redirecting?: boolean }> {
  if (Platform.OS === 'web') {
    const redirectUrl = window.location.origin + window.location.pathname;
    window.location.href = `${EMERGENT_AUTH}?redirect=${encodeURIComponent(redirectUrl)}`;
    return { ok: false, redirecting: true };
  }
  const redirectUrl = Linking.createURL('');
  const authUrl = `${EMERGENT_AUTH}?redirect=${encodeURIComponent(redirectUrl)}`;
  const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
  if (result.type !== 'success' || !result.url) {
    return { ok: false, error: 'cancelled' };
  }
  const sid = parseSessionId(result.url);
  if (!sid) return { ok: false, error: 'No session returned' };
  return exchangeSession(sid);
}

export async function logout(): Promise<void> {
  try { await api.post('/api/auth/logout', {}, { headers: authHeaders(), timeoutMs: 8000 }); } catch {}
  await persist('');
}
