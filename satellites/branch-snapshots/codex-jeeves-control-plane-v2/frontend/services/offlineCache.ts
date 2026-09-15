/**
 * Offline Cache Service — ULTRASCALE
 * Fetches all collections from /api/academy/offline/manifest and /offline/dump
 * Stores in AsyncStorage for complete offline operation
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const CACHE_VERSION_KEY = '@tutolage_cache_version';
const CACHE_PREFIX = '@tutolage_offline_';
const CACHE_MANIFEST_KEY = '@tutolage_manifest';
const CURRENT_VERSION = '2026-SOTA-v2';

export interface CacheManifest {
  collections: Record<string, number>;
  total_documents: number;
  version: string;
  cacheable: boolean;
}

export interface CacheProgress {
  collection: string;
  downloaded: number;
  total: number;
  percentage: number;
}

export type ProgressCallback = (progress: CacheProgress) => void;

/**
 * Check if offline data is already cached
 */
export async function isCacheValid(): Promise<boolean> {
  try {
    const version = await AsyncStorage.getItem(CACHE_VERSION_KEY);
    if (version !== CURRENT_VERSION) return false;
    const manifest = await AsyncStorage.getItem(CACHE_MANIFEST_KEY);
    return !!manifest;
  } catch {
    return false;
  }
}

/**
 * Get the cached manifest (collection names + counts)
 */
export async function getCachedManifest(): Promise<CacheManifest | null> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_MANIFEST_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * Fetch manifest from backend
 */
export async function fetchManifest(): Promise<CacheManifest | null> {
  try {
    const res = await fetch(`${API}/api/academy/offline/manifest`);
    if (res.ok) return await res.json();
    return null;
  } catch {
    return null;
  }
}

/**
 * Download a single collection in pages and store in AsyncStorage
 */
async function downloadCollection(
  collection: string,
  totalDocs: number,
  onProgress?: ProgressCallback
): Promise<boolean> {
  const PAGE_SIZE = 500;
  let allDocs: any[] = [];
  let skip = 0;

  while (skip < totalDocs) {
    try {
      const res = await fetch(`${API}/api/academy/offline/dump/${collection}?skip=${skip}&limit=${PAGE_SIZE}`);
      if (!res.ok) break;
      const data = await res.json();
      const docs = data.documents || [];
      allDocs = allDocs.concat(docs);
      skip += docs.length;

      onProgress?.({
        collection,
        downloaded: allDocs.length,
        total: totalDocs,
        percentage: Math.round((allDocs.length / totalDocs) * 100),
      });

      if (!data.has_more || docs.length === 0) break;
    } catch {
      break;
    }
  }

  // Store in AsyncStorage — chunk large collections
  try {
    const CHUNK_SIZE = 200;
    const chunks = Math.ceil(allDocs.length / CHUNK_SIZE);
    for (let i = 0; i < chunks; i++) {
      const chunk = allDocs.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
      await AsyncStorage.setItem(
        `${CACHE_PREFIX}${collection}_${i}`,
        JSON.stringify(chunk)
      );
    }
    await AsyncStorage.setItem(
      `${CACHE_PREFIX}${collection}_meta`,
      JSON.stringify({ total: allDocs.length, chunks, cachedAt: new Date().toISOString() })
    );
    return true;
  } catch {
    return false;
  }
}

/**
 * Download ALL collections for full offline mode
 */
export async function syncAllOfflineData(
  onProgress?: (overall: { collection: string; collectionIndex: number; totalCollections: number; docProgress: CacheProgress }) => void
): Promise<{ success: boolean; collections: number; documents: number }> {
  const manifest = await fetchManifest();
  if (!manifest) return { success: false, collections: 0, documents: 0 };

  const collections = Object.entries(manifest.collections);
  let totalDocs = 0;
  let successCount = 0;

  for (let i = 0; i < collections.length; i++) {
    const [name, count] = collections[i];
    if (count === 0) { successCount++; continue; }

    const ok = await downloadCollection(name, count, (docProgress) => {
      onProgress?.({
        collection: name,
        collectionIndex: i,
        totalCollections: collections.length,
        docProgress,
      });
    });

    if (ok) {
      successCount++;
      totalDocs += count;
    }
  }

  // Store manifest and version
  await AsyncStorage.setItem(CACHE_MANIFEST_KEY, JSON.stringify(manifest));
  await AsyncStorage.setItem(CACHE_VERSION_KEY, CURRENT_VERSION);

  return { success: successCount === collections.length, collections: successCount, documents: totalDocs };
}

/**
 * Get cached data for a collection
 */
export async function getCachedCollection(collection: string): Promise<any[]> {
  try {
    const metaRaw = await AsyncStorage.getItem(`${CACHE_PREFIX}${collection}_meta`);
    if (!metaRaw) return [];
    const meta = JSON.parse(metaRaw);
    const allDocs: any[] = [];
    for (let i = 0; i < meta.chunks; i++) {
      const chunkRaw = await AsyncStorage.getItem(`${CACHE_PREFIX}${collection}_${i}`);
      if (chunkRaw) {
        allDocs.push(...JSON.parse(chunkRaw));
      }
    }
    return allDocs;
  } catch {
    return [];
  }
}

/**
 * Clear all cached offline data
 */
export async function clearOfflineCache(): Promise<void> {
  try {
    const keys = await AsyncStorage.getAllKeys();
    const cacheKeys = keys.filter(k => k.startsWith(CACHE_PREFIX) || k === CACHE_VERSION_KEY || k === CACHE_MANIFEST_KEY);
    if (cacheKeys.length > 0) {
      await AsyncStorage.multiRemove(cacheKeys);
    }
  } catch {}
}

/**
 * Get cache stats
 */
export async function getCacheStats(): Promise<{
  isCached: boolean;
  version: string | null;
  collections: number;
  totalDocs: number;
  cachedAt: string | null;
}> {
  try {
    const version = await AsyncStorage.getItem(CACHE_VERSION_KEY);
    const manifestRaw = await AsyncStorage.getItem(CACHE_MANIFEST_KEY);
    if (!manifestRaw) return { isCached: false, version: null, collections: 0, totalDocs: 0, cachedAt: null };

    const manifest: CacheManifest = JSON.parse(manifestRaw);
    const keys = await AsyncStorage.getAllKeys();
    const metaKeys = keys.filter(k => k.startsWith(CACHE_PREFIX) && k.endsWith('_meta'));

    let totalDocs = 0;
    let latestDate: string | null = null;
    for (const key of metaKeys) {
      const raw = await AsyncStorage.getItem(key);
      if (raw) {
        const meta = JSON.parse(raw);
        totalDocs += meta.total || 0;
        if (!latestDate || meta.cachedAt > latestDate) latestDate = meta.cachedAt;
      }
    }

    return {
      isCached: version === CURRENT_VERSION,
      version,
      collections: metaKeys.length,
      totalDocs,
      cachedAt: latestDate,
    };
  } catch {
    return { isCached: false, version: null, collections: 0, totalDocs: 0, cachedAt: null };
  }
}
