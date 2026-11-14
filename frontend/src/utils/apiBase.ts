/**
 * Canonical runtime endpoint resolution for the assembled application.
 *
 * Resolution order is intentionally identical for every frontend client:
 *   1. explicit EXPO_PUBLIC_* / legacy Expo extra override,
 *   2. browser same-origin fallback (for reverse-proxied deployments),
 *   3. local development port on web only (never native-device loopback).
 *
 * Explicit values win on web as well as native. This is important for the
 * Docker/Expo development topology where the browser runs on :3000 while the
 * application API and Skeleton engine live on :8001 and :8010.
 */
import { Platform } from 'react-native';
import Constants from 'expo-constants';

type EndpointKey =
  | 'EXPO_PUBLIC_BACKEND_URL'
  | 'EXPO_BACKEND_URL'
  | 'EXPO_PUBLIC_SKELETON_URL'
  | 'EXPO_SKELETON_URL'
  | 'EXPO_PUBLIC_BACKEND_FALLBACK_URL';

function clean(value: unknown): string {
  return typeof value === 'string' ? value.trim().replace(/\/+$/, '') : '';
}

function extraValue(key: EndpointKey): string {
  const expoConfig = (Constants?.expoConfig as any)?.extra;
  const manifest = (Constants as any)?.manifest?.extra;
  return clean(expoConfig?.[key] || manifest?.[key] || '');
}

function processValue(key: EndpointKey): string {
  switch (key) {
    case 'EXPO_PUBLIC_BACKEND_URL':
      return clean(process.env.EXPO_PUBLIC_BACKEND_URL);
    case 'EXPO_BACKEND_URL':
      return clean(process.env.EXPO_BACKEND_URL);
    case 'EXPO_PUBLIC_SKELETON_URL':
      return clean(process.env.EXPO_PUBLIC_SKELETON_URL);
    case 'EXPO_SKELETON_URL':
      return clean(process.env.EXPO_SKELETON_URL);
    case 'EXPO_PUBLIC_BACKEND_FALLBACK_URL':
      return clean(process.env.EXPO_PUBLIC_BACKEND_FALLBACK_URL);
  }
}

function explicitEndpoint(keys: EndpointKey[]): string {
  for (const key of keys) {
    const fromProcess = processValue(key);
    if (fromProcess) return fromProcess;
    const fromExtra = extraValue(key);
    if (fromExtra) return fromExtra;
  }
  return '';
}

function browserOrigin(): string {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return '';
  const origin = clean((window as any)?.location?.origin);
  if (!origin || origin.startsWith('file:')) return '';
  return origin;
}

function resolveEndpoint(keys: EndpointKey[], localFallback: string): string {
  const explicit = explicitEndpoint(keys);
  if (explicit) return allowedInstalledEndpoint(explicit) ? explicit : '';

  const sameOrigin = browserOrigin();
  if (sameOrigin) return sameOrigin;

  // Browser development can use a loopback API; a phone installation must
  // carry an explicit reachable backend origin supplied at build time.
  return Platform.OS === 'web' ? localFallback : '';
}

function allowedInstalledEndpoint(value: string): boolean {
  if (!value || Platform.OS === 'web') return true;
  try {
    const endpoint = new URL(value);
    const host = endpoint.hostname.toLowerCase();
    const local = host === 'localhost' || host === '0.0.0.0'
      || host === '[::1]' || /^127\./.test(host) || host === '10.0.2.2';
    const development = typeof __DEV__ !== 'undefined' && __DEV__ === true;
    return (!local || development) && (endpoint.protocol === 'https:' || development && endpoint.protocol === 'http:')
      && !endpoint.username && !endpoint.password && !endpoint.search && !endpoint.hash
      && (endpoint.pathname === '/' || endpoint.pathname === '');
  } catch { return false; }
}

export const API_BASE = resolveEndpoint(
  ['EXPO_PUBLIC_BACKEND_URL', 'EXPO_BACKEND_URL'],
  'http://localhost:8001',
);

export const SKELETON_API_BASE = resolveEndpoint(
  ['EXPO_PUBLIC_SKELETON_URL', 'EXPO_SKELETON_URL'],
  'http://localhost:8010',
);

/** Diagnose unconnected native installs without sending any credentials. */
export function nativeBackendConfigurationIssue(): string | null {
  if (Platform.OS === 'web' || API_BASE) return null;
  return 'This installed app has no usable backend connection. Rebuild it with '
    + 'EXPO_PUBLIC_BACKEND_URL set to your reachable HTTPS application API '
    + 'origin. localhost points to the phone, not the Skeleton host.';
}

export const API_FALLBACK_BASE = explicitEndpoint([
  'EXPO_PUBLIC_BACKEND_FALLBACK_URL',
]);

export const RUNTIME_ENDPOINTS = Object.freeze({
  backend: API_BASE,
  backendFallback: API_FALLBACK_BASE,
  skeleton: SKELETON_API_BASE,
});

/** Build a backend URL from a relative path or preserve an absolute URL. */
export function api(path: string): string {
  if (!path) return API_BASE;
  if (/^https?:\/\//i.test(path)) return path;
  return API_BASE + (path.startsWith('/') ? path : '/' + path);
}

/** Build a Skeleton-engine URL from a relative path or preserve an absolute URL. */
export function skeletonApi(path: string): string {
  if (!path) return SKELETON_API_BASE;
  if (/^https?:\/\//i.test(path)) return path;
  return SKELETON_API_BASE + (path.startsWith('/') ? path : '/' + path);
}
