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

export function getAuthToken(): string {
  return _token;
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return _token ? { Authorization: `Bearer ${_token}`, ...extra } : { ...extra };
}

async function persist(token: string) {
  _token = token;
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

async function loadStored(): Promise<string> {
  try {
    if (Platform.OS === 'web') return localStorage.getItem(KEY) || '';
    return (await SecureStore.getItemAsync(KEY)) || '';
  } catch {
    return '';
  }
}

export interface MeResult {
  authenticated: boolean;
  enforced: boolean;
  role: string;
  user: any;
}

/** Validate the current token against the backend. Clears it on 401. */
export async function checkMe(): Promise<MeResult> {
  const stored = _token || (await loadStored());
  _token = stored;
  const r = await api.get<any>('/api/auth/me', stored ? { headers: authHeaders() } : {});
  if (!r.ok) return { authenticated: false, enforced: false, role: 'anonymous', user: null };
  if (r.status === 401) { await persist(''); }
  const authed = !!r.data?.authenticated;
  return {
    authenticated: authed,
    enforced: !!r.data?.enforced,
    role: r.data?.user?.role || 'anonymous',
    user: authed ? r.data?.user : null,
  };
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
