/**
 * apiBase — pick the right backend origin per platform.
 *
 *  • Web: when the app is loaded from a real origin (preview, deployed,
 *    custom domain), prefer SAME-ORIGIN so `/api/*` is routed by the
 *    platform ingress to the backend (port 8001). This makes the app
 *    work on every URL — no env edit required when deploying.
 *
 *  • Native (Expo Go / installed APK): use EXPO_PUBLIC_BACKEND_URL from
 *    the bundled .env. There is no "current origin" on native.
 *
 *  • Fallback: localhost:8001 for local dev where neither is set.
 */
import { Platform } from 'react-native';
import Constants from 'expo-constants';

function resolveApiBase(): string {
  // 1) Web — use the page's own origin so requests hit the same host
  //    the bundle was loaded from. The platform ingress maps /api/* to
  //    the backend service.
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    const loc: any = (window as any).location;
    if (loc && typeof loc.origin === 'string' && loc.origin && !loc.origin.startsWith('file:')) {
      return loc.origin.replace(/\/+$/, '');
    }
  }
  // 2) Native or fallback — use the env-baked URL
  const envFromConst =
    (Constants?.expoConfig as any)?.extra?.EXPO_PUBLIC_BACKEND_URL ||
    (Constants as any)?.manifest?.extra?.EXPO_PUBLIC_BACKEND_URL ||
    '';
  const envFromProcess = (process.env.EXPO_PUBLIC_BACKEND_URL || '').trim();
  const env = (envFromConst || envFromProcess || '').replace(/\/+$/, '');
  if (env) return env;
  // 3) Last-ditch local dev fallback
  return 'http://localhost:8001';
}

export const API_BASE = resolveApiBase();

/** Convenience: build a full URL from a path that may or may not start with /. */
export function api(path: string): string {
  if (!path) return API_BASE;
  if (/^https?:\/\//i.test(path)) return path;
  return API_BASE + (path.startsWith('/') ? path : '/' + path);
}
