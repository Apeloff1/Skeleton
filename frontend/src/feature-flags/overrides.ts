/**
 * src/feature-flags/overrides.ts — local per-device flag overrides.
 *
 * Two layers of override sit ABOVE the server response:
 *
 *   1. URL-query override — e.g. `?ff=hub.network_banner:on,boot.starfall_background:off`
 *      Parsed once at boot (web only). Persists for the session only.
 *      Handy for QA / bug repro links.
 *
 *   2. Per-device override — written from the FF admin screen via the
 *      `setLocalOverride` helper. Backed by AsyncStorage so it survives
 *      restarts. Cleared via `clearLocalOverrides`.
 *
 * Both layers are MERGED on top of the server snapshot inside
 * FeatureFlagProvider — final precedence: query > local > server.
 */
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = '@ff/local_overrides:v1';

function parseQueryString(qs: string): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  if (!qs) return out;
  for (const part of qs.split(',')) {
    const [name, value] = part.split(':');
    if (!name) continue;
    const v = String(value || '').toLowerCase();
    if (v === '1' || v === 'on' || v === 'true' || v === 'yes') out[name.trim()] = true;
    else if (v === '0' || v === 'off' || v === 'false' || v === 'no') out[name.trim()] = false;
  }
  return out;
}

let _queryOverrides: Record<string, boolean> | null = null;

export function getQueryOverrides(): Record<string, boolean> {
  if (_queryOverrides !== null) return _queryOverrides;
  _queryOverrides = {};
  if (Platform.OS !== 'web') return _queryOverrides;
  try {
    const url = typeof window !== 'undefined' ? window.location?.search : '';
    if (!url) return _queryOverrides;
    const params = new URLSearchParams(url);
    _queryOverrides = parseQueryString(params.get('ff') || '');
  } catch {
    _queryOverrides = {};
  }
  return _queryOverrides;
}

let _localCache: Record<string, boolean> | null = null;

export async function loadLocalOverrides(): Promise<Record<string, boolean>> {
  if (_localCache) return _localCache;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    _localCache = raw ? JSON.parse(raw) : {};
  } catch { _localCache = {}; }
  return _localCache!;
}

export function getLocalOverridesCached(): Record<string, boolean> {
  return _localCache || {};
}

export async function setLocalOverride(name: string, value: boolean | null): Promise<void> {
  const cur = await loadLocalOverrides();
  if (value === null) delete cur[name]; else cur[name] = !!value;
  _localCache = { ...cur };
  try { await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(_localCache)); } catch { /* swallow */ }
}

export async function clearLocalOverrides(): Promise<void> {
  _localCache = {};
  try { await AsyncStorage.removeItem(STORAGE_KEY); } catch { /* swallow */ }
}
