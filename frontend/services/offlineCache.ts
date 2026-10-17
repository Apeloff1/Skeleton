/**
 * Transactional, bounded-memory academy offline cache.
 *
 * A durable commit pointer is the only authority for a newly synchronized
 * generation. Pages are written to an isolated staging namespace; failures,
 * app termination, cancellation and partial HTTP responses cannot make an
 * incomplete generation appear ready. The previous committed generation
 * remains readable until all new collection metadata has been persisted.
 */
import { API_BASE as CANONICAL_API_BASE } from '../utils/apiBase';
import AsyncStorage from '@react-native-async-storage/async-storage';

const API = CANONICAL_API_BASE;
const CACHE_VERSION_KEY = '@tutolage_cache_version';
const CACHE_PREFIX = '@tutolage_offline_';
const CACHE_MANIFEST_KEY = '@tutolage_manifest';
const COMMIT_KEY = '@tutolage_offline_commit:v1';
const CURRENT_VERSION = '2026-SOTA-v2';
const PAGE_SIZE = 100;
const MAX_PAGE_CHARS = 1024 * 1024;
const MAX_READ_DOCS = 20_000;
const MAX_COLLECTIONS = 5_000;
const MAX_COLLECTION_DOCS = 2_000_000;
const FETCH_TIMEOUT_MS = 15_000;

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

interface CacheCommit {
  version: string;
  generation: string;
  manifest: CacheManifest;
  committedAt: string;
}
interface CollectionMeta {
  total: number;
  chunks: number;
  cachedAt: string;
}
type OverallProgress = {
  collection: string;
  collectionIndex: number;
  totalCollections: number;
  docProgress: CacheProgress;
};
type SyncResult = { success: boolean; collections: number; documents: number };

let activeSync: Promise<SyncResult> | null = null;
let syncController: AbortController | null = null;
let clearing = false;

function collectionName(value: string): boolean {
  return /^[A-Za-z0-9_.-]{1,120}$/.test(value) && !value.includes('..');
}
function nonnegativeInt(value: unknown, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0 && Number(value) <= max;
}
function validateManifest(raw: unknown): CacheManifest | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const m = raw as CacheManifest;
  if (!m.cacheable || !m.collections || typeof m.collections !== 'object' ||
      Array.isArray(m.collections) || typeof m.version !== 'string') return null;
  const entries = Object.entries(m.collections);
  if (entries.length > MAX_COLLECTIONS || !nonnegativeInt(m.total_documents, Number.MAX_SAFE_INTEGER)) return null;
  let total = 0;
  for (const [key, count] of entries) {
    if (!collectionName(key) || !nonnegativeInt(count, MAX_COLLECTION_DOCS)) return null;
    total += count;
  }
  if (total !== m.total_documents) return null;
  return m;
}
function validCommit(raw: string | null): CacheCommit | null {
  if (!raw) return null;
  try {
    const c = JSON.parse(raw) as CacheCommit;
    if (c?.version !== CURRENT_VERSION || !/^[0-9a-z-]{8,80}$/.test(c.generation) ||
        !validateManifest(c.manifest) || !Number.isFinite(Date.parse(c.committedAt))) return null;
    return c;
  } catch { return null; }
}
async function committed(): Promise<CacheCommit | null> {
  return validCommit(await AsyncStorage.getItem(COMMIT_KEY));
}
function baseKey(collection: string, generation: string | null): string {
  return generation ? `${CACHE_PREFIX}g-${generation}/${collection}` : `${CACHE_PREFIX}${collection}`;
}
async function getStoredMeta(collection: string, generation: string | null): Promise<CollectionMeta | null> {
  const raw = await AsyncStorage.getItem(baseKey(collection, generation) + '_meta');
  if (!raw || raw.length > 4096) return null;
  try {
    const v = JSON.parse(raw) as CollectionMeta;
    if (!nonnegativeInt(v.total, MAX_COLLECTION_DOCS) ||
        !nonnegativeInt(v.chunks, MAX_COLLECTION_DOCS) ||
        (v.total > 0 && v.chunks === 0) || typeof v.cachedAt !== 'string') return null;
    return v;
  } catch { return null; }
}
async function activeManifest(): Promise<{ manifest: CacheManifest; generation: string | null } | null> {
  const rawCommit = await AsyncStorage.getItem(COMMIT_KEY);
  if (rawCommit !== null) {
    const current = validCommit(rawCommit);
    return current ? { manifest: current.manifest, generation: current.generation } : null;
  }
  // Backwards-compatible reads for installations with a pre-transactional cache.
  if (await AsyncStorage.getItem(CACHE_VERSION_KEY) !== CURRENT_VERSION) return null;
  const raw = await AsyncStorage.getItem(CACHE_MANIFEST_KEY);
  if (!raw) return null;
  try {
    const manifest = validateManifest(JSON.parse(raw));
    return manifest ? { manifest, generation: null } : null;
  } catch { return null; }
}

export async function isCacheValid(): Promise<boolean> {
  try {
    const active = await activeManifest();
    if (!active) return false;
    for (const [name, count] of Object.entries(active.manifest.collections)) {
      if (count === 0) continue;
      const meta = await getStoredMeta(name, active.generation);
      if (!meta || meta.total !== count || meta.chunks === 0) return false;
    }
    return true;
  } catch { return false; }
}

export async function getCachedManifest(): Promise<CacheManifest | null> {
  try { return (await activeManifest())?.manifest ?? null; }
  catch { return null; }
}

async function requestJson(url: string, signal?: AbortSignal): Promise<unknown> {
  if (!API) throw new Error('Backend unavailable');
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  let rejectOnAbort: (() => void) | null = null;
  const abortPromise = new Promise<never>((_resolve, reject) => {
    rejectOnAbort = () => reject(new Error('Offline request aborted'));
    if (controller.signal.aborted) rejectOnAbort();
    else controller.signal.addEventListener('abort', rejectOnAbort, { once: true });
  });
  try {
    // Abort must settle the caller even when an outdated fetch shim ignores
    // AbortSignal entirely; a late response can never write staged data.
    const response = await Promise.race([fetch(url, { signal: controller.signal }), abortPromise]);
    if (!response.ok || controller.signal.aborted) throw new Error('Offline endpoint unavailable');
    const declared = Number(response.headers?.get?.('content-length'));
    if (Number.isFinite(declared) && declared > MAX_PAGE_CHARS) throw new Error('Oversized offline page');
    const text = await Promise.race([response.text(), abortPromise]);
    if (controller.signal.aborted || text.length > MAX_PAGE_CHARS) throw new Error('Offline page invalid');
    return JSON.parse(text);
  } finally {
    clearTimeout(timer);
    if (rejectOnAbort) controller.signal.removeEventListener('abort', rejectOnAbort);
    signal?.removeEventListener('abort', onAbort);
  }
}

export async function fetchManifest(): Promise<CacheManifest | null> {
  try { return validateManifest(await requestJson(`${API}/api/academy/offline/manifest`)); }
  catch { return null; }
}

async function downloadCollection(
  collection: string,
  totalDocs: number,
  generation: string,
  signal: AbortSignal,
  onProgress?: ProgressCallback,
): Promise<boolean> {
  const prefix = baseKey(collection, generation);
  let skip = 0;
  let chunks = 0;
  while (skip < totalDocs) {
    if (signal.aborted) return false;
    try {
      const page = await requestJson(
        `${API}/api/academy/offline/dump/${encodeURIComponent(collection)}?skip=${skip}&limit=${PAGE_SIZE}`, signal,
      ) as { documents?: unknown; has_more?: unknown };
      const docs = page?.documents;
      // The reader's chunk offsets are fixed at PAGE_SIZE; reject short
      // nonterminal pages rather than silently shifting later offsets.
      if (!Array.isArray(docs) ||
          docs.length !== Math.min(PAGE_SIZE, totalDocs - skip)) return false;
      const chunk = JSON.stringify(docs);
      if (chunk.length > MAX_PAGE_CHARS) return false;
      if (signal.aborted) return false;
      await AsyncStorage.setItem(prefix + '_' + chunks, chunk);
      chunks++;
      skip += docs.length;
      // Server claiming no more pages before the manifest count is reached
      // indicates truncation. Do not publish incomplete cache data.
      if (skip < totalDocs && page.has_more === false) return false;
      try {
        onProgress?.({
          collection, downloaded: skip, total: totalDocs,
          percentage: Math.round(skip / totalDocs * 100),
        });
      } catch { /* UI subscriber must not cancel a committed download */ }
    } catch { return false; }
  }
  if (signal.aborted || skip !== totalDocs) return false;
  await AsyncStorage.setItem(prefix + '_meta', JSON.stringify({
    total: skip, chunks, cachedAt: new Date().toISOString(),
  } satisfies CollectionMeta));
  return true;
}

async function removeKeys(keys: string[]): Promise<void> {
  for (let i = 0; i < keys.length; i += 100) {
    await AsyncStorage.multiRemove(keys.slice(i, i + 100));
  }
}
async function removeStagedGeneration(generation: string): Promise<void> {
  try {
    const prefix = CACHE_PREFIX + 'g-' + generation + '/';
    // A successful generation is authoritative after commit. Never delete it
    // from an old cleanup callback; deleting another sync's staging is unsafe.
    const current = await committed();
    if (current?.generation === generation) return;
    const keys = await AsyncStorage.getAllKeys();
    await removeKeys(keys.filter(key => key.startsWith(prefix)));
  } catch { /* best effort */ }
}

async function runSync(onProgress?: (overall: OverallProgress) => void, signal?: AbortSignal): Promise<SyncResult> {
  const invalid: SyncResult = { success: false, collections: 0, documents: 0 };
  const controller = new AbortController();
  syncController = controller;
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort, { once: true });
  if (signal?.aborted) controller.abort();
  const generation = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  let committedSuccessfully = false;
  try {
    const manifest = validateManifest(await requestJson(`${API}/api/academy/offline/manifest`, controller.signal));
    if (!manifest || controller.signal.aborted) return invalid;
    const collections = Object.entries(manifest.collections);
    let completed = 0;
    let documents = 0;
    for (let index = 0; index < collections.length; index++) {
      const [collection, expected] = collections[index];
      if (controller.signal.aborted) return { success: false, collections: completed, documents };
      if (expected > 0) {
        const ok = await downloadCollection(collection, expected, generation, controller.signal, progress => {
          try {
            onProgress?.({ collection, collectionIndex: index, totalCollections: collections.length, docProgress: progress });
          } catch { /* subscriber isolation */ }
        });
        if (!ok) return { success: false, collections: completed, documents };
      }
      completed++;
      documents += expected;
    }
    if (controller.signal.aborted) return { success: false, collections: completed, documents };
    const commit: CacheCommit = {
      version: CURRENT_VERSION, generation, manifest, committedAt: new Date().toISOString(),
    };
    // LAST authoritative write: after every page and metadata row completed.
    await AsyncStorage.setItem(COMMIT_KEY, JSON.stringify(commit));
    committedSuccessfully = true;
    return { success: true, collections: completed, documents };
  } catch { return invalid; }
  finally {
    signal?.removeEventListener('abort', onAbort);
    if (syncController === controller) syncController = null;
    // Do not delete a prior committed generation from a detached callback:
    // older readers may have captured its pointer before this transaction.
    // An incomplete staging namespace is always safe to remove by exact ID.
    if (!committedSuccessfully) void removeStagedGeneration(generation);
  }
}

/** Repeated sync requests share a single transaction. */
export function syncAllOfflineData(
  onProgress?: (overall: OverallProgress) => void,
  options: { signal?: AbortSignal } = {},
): Promise<SyncResult> {
  if (clearing) return Promise.resolve({ success: false, collections: 0, documents: 0 });
  if (activeSync) return activeSync;
  const work = runSync(onProgress, options.signal);
  activeSync = work;
  const release = () => { if (activeSync === work) activeSync = null; };
  void work.then(release, release);
  return work;
}

export function cancelOfflineSync(): void {
  syncController?.abort();
}

export async function getCachedCollectionPage(
  collection: string, skip = 0, limit = PAGE_SIZE,
): Promise<unknown[]> {
  if (!collectionName(collection) || !nonnegativeInt(skip, MAX_COLLECTION_DOCS) ||
      !nonnegativeInt(limit, 1000) || limit === 0) return [];
  try {
    const active = await activeManifest();
    if (!active || !(collection in active.manifest.collections)) return [];
    const expected = active.manifest.collections[collection];
    const meta = await getStoredMeta(collection, active.generation);
    if (!meta || meta.total !== expected || skip >= expected) return [];
    const first = Math.floor(skip / PAGE_SIZE);
    const end = Math.min(meta.chunks, Math.ceil((skip + limit) / PAGE_SIZE));
    const result: unknown[] = [];
    for (let chunk = first; chunk < end; chunk++) {
      const raw = await AsyncStorage.getItem(baseKey(collection, active.generation) + '_' + chunk);
      if (!raw || raw.length > MAX_PAGE_CHARS) return [];
      const docs = JSON.parse(raw);
      if (!Array.isArray(docs) || docs.length > PAGE_SIZE) return [];
      result.push(...docs);
    }
    return result.slice(skip % PAGE_SIZE, skip % PAGE_SIZE + limit);
  } catch { return []; }
}

/**
 * Compatibility API for small collections. Large collections must be paged
 * through getCachedCollectionPage; returning a partial array would be unsafe.
 */
export async function getCachedCollection(collection: string): Promise<any[]> {
  try {
    const active = await activeManifest();
    if (!active || !collectionName(collection)) return [];
    const expected = active.manifest.collections[collection];
    if (!nonnegativeInt(expected, MAX_READ_DOCS)) return [];
    const result: unknown[] = [];
    for (let skip = 0; skip < expected; skip += PAGE_SIZE) {
      const docs = await getCachedCollectionPage(collection, skip, PAGE_SIZE);
      if (docs.length !== Math.min(PAGE_SIZE, expected - skip)) return [];
      result.push(...docs);
    }
    return result;
  } catch { return []; }
}

/** Stop synchronization before deleting any owned cache rows. */
export async function clearOfflineCache(): Promise<void> {
  clearing = true;
  try {
    cancelOfflineSync();
    if (activeSync) await activeSync.catch(() => {});
    await AsyncStorage.removeItem(COMMIT_KEY);
    const keys = await AsyncStorage.getAllKeys();
    const owned = keys.filter(key => key.startsWith(CACHE_PREFIX) ||
      key === CACHE_VERSION_KEY || key === CACHE_MANIFEST_KEY);
    await removeKeys(owned);
  } finally { clearing = false; }
}

export async function getCacheStats(): Promise<{
  isCached: boolean;
  version: string | null;
  collections: number;
  totalDocs: number;
  cachedAt: string | null;
}> {
  try {
    const active = await activeManifest();
    if (!active) return {
      isCached: false, version: null, collections: 0, totalDocs: 0, cachedAt: null,
    };
    const manifest = active.manifest;
    let latestDate: string | null = null;
    for (const name of Object.keys(manifest.collections)) {
      if (!manifest.collections[name]) continue;
      const meta = await getStoredMeta(name, active.generation);
      if (!meta || meta.total !== manifest.collections[name]) {
        return { isCached: false, version: CURRENT_VERSION, collections: 0, totalDocs: 0, cachedAt: null };
      }
      if (!latestDate || meta.cachedAt > latestDate) latestDate = meta.cachedAt;
    }
    return {
      isCached: true, version: CURRENT_VERSION,
      collections: Object.keys(manifest.collections).length,
      totalDocs: manifest.total_documents, cachedAt: latestDate,
    };
  } catch {
    return { isCached: false, version: null, collections: 0, totalDocs: 0, cachedAt: null };
  }
}
