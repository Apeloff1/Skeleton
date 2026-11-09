/**
 * src/feature-flags/adminToken.ts — per-device admin token storage.
 *
 * The backend gates POST/DELETE behind FEATURE_FLAGS_ADMIN_TOKEN when
 * that env var is set. Power users / QA paste their token into the
 * admin screen once; we persist it in AsyncStorage and inject it on
 * every mutation request via the apiClient `headers` option.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = '@ff/admin_token:v1';
let _cache: string | null = null;

export async function loadAdminToken(): Promise<string> {
  if (_cache !== null) return _cache;
  try { _cache = (await AsyncStorage.getItem(KEY)) || ''; }
  catch { _cache = ''; }
  return _cache;
}

export function getAdminTokenCached(): string {
  return _cache || '';
}

export async function setAdminToken(token: string): Promise<void> {
  _cache = token || '';
  try {
    if (_cache) await AsyncStorage.setItem(KEY, _cache);
    else        await AsyncStorage.removeItem(KEY);
  } catch { /* swallow */ }
}

export function adminHeaders(): Record<string, string> {
  const t = getAdminTokenCached();
  return t ? { 'X-Admin-Token': t } : {};
}
