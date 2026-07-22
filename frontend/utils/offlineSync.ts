/**
 * Offline Sync — downloads the entire Academy reading-content corpus to local
 * device storage so the Reading Visualizer can serve every chapter without a
 * network round-trip. Works on BOTH Expo Web (IndexedDB-backed AsyncStorage)
 * AND native APKs (SQLite-backed AsyncStorage), giving uniform behaviour.
 *
 * Storage layout (AsyncStorage keys):
 *   @codedock:offline:manifest                 → JSON manifest (work plan)
 *   @codedock:offline:state                    → SyncState (status/progress)
 *   @codedock:offline:ch:<itemKey>:<idx>       → chapter JSON payload
 *   @codedock:offline:keys                     → JSON array index of every
 *                                                chapter key (for footprint)
 *
 * On first open, getCachedChapter(itemKey, idx) returns the on-disk
 * payload if present; the ReadingVisualizer falls back to network when missing.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_BASE } from './apiBase';

const API = API_BASE;
const PREFIX = '@codedock:offline:';
const MANIFEST_KEY = PREFIX + 'manifest';
const STATE_KEY = PREFIX + 'state';
const KEYS_INDEX = PREFIX + 'keys';
const chapKey = (itemKey: string, idx: number) =>
  `${PREFIX}ch:${itemKey.replace(/[^a-zA-Z0-9_:.-]/g, '_')}:${idx}`;

export interface SyncState {
  status: 'idle' | 'downloading' | 'completed' | 'failed' | 'paused';
  total: number;
  downloaded: number;
  manifest_books: number;
  manifest_chapters: number;
  last_run: string | null;
  error: string | null;
  errors_count?: number;
}

const DEFAULT_STATE: SyncState = {
  status: 'idle',
  total: 0,
  downloaded: 0,
  manifest_books: 0,
  manifest_chapters: 0,
  last_run: null,
  error: null,
  errors_count: 0,
};

let abort = false;

// ─── Index management ───────────────────────────────────────────────
async function readKeysIndex(): Promise<Set<string>> {
  try {
    const raw = await AsyncStorage.getItem(KEYS_INDEX);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    if (Array.isArray(arr)) return new Set(arr);
    return new Set();
  } catch {
    return new Set();
  }
}

async function writeKeysIndex(s: Set<string>): Promise<void> {
  try {
    await AsyncStorage.setItem(KEYS_INDEX, JSON.stringify([...s]));
  } catch {
    // ignore
  }
}

async function addKeyToIndex(k: string): Promise<void> {
  const s = await readKeysIndex();
  if (!s.has(k)) {
    s.add(k);
    await writeKeysIndex(s);
  }
}

async function removeKeyFromIndex(k: string): Promise<void> {
  const s = await readKeysIndex();
  if (s.has(k)) {
    s.delete(k);
    await writeKeysIndex(s);
  }
}

// ─── Public API ─────────────────────────────────────────────────────
export async function getSyncState(): Promise<SyncState> {
  try {
    const raw = await AsyncStorage.getItem(STATE_KEY);
    if (!raw) return DEFAULT_STATE;
    return { ...DEFAULT_STATE, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_STATE;
  }
}

async function setSyncState(patch: Partial<SyncState>): Promise<SyncState> {
  const cur = await getSyncState();
  const next = { ...cur, ...patch };
  await AsyncStorage.setItem(STATE_KEY, JSON.stringify(next));
  return next;
}

export async function getCachedChapter(itemKey: string, chapterIdx: number): Promise<any | null> {
  try {
    const raw = await AsyncStorage.getItem(chapKey(itemKey, chapterIdx));
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function isChapterCached(itemKey: string, chapterIdx: number): Promise<boolean> {
  try {
    const v = await AsyncStorage.getItem(chapKey(itemKey, chapterIdx));
    return v != null;
  } catch {
    return false;
  }
}

export async function saveChapterOffline(
  itemKey: string,
  chapterIdx: number,
  payload: any,
): Promise<boolean> {
  try {
    const k = chapKey(itemKey, chapterIdx);
    await AsyncStorage.setItem(k, JSON.stringify(payload));
    await addKeyToIndex(k);
    return true;
  } catch {
    return false;
  }
}

export async function deleteChapterOffline(itemKey: string, chapterIdx: number): Promise<void> {
  try {
    const k = chapKey(itemKey, chapterIdx);
    await AsyncStorage.removeItem(k);
    await removeKeyFromIndex(k);
  } catch {
    // ignore
  }
}

export async function clearOfflineCache(): Promise<void> {
  try {
    const idx = await readKeysIndex();
    if (idx.size > 0) {
      const keys = [...idx];
      // multiRemove in chunks of 200 to avoid native bridge limits
      const CHUNK = 200;
      for (let i = 0; i < keys.length; i += CHUNK) {
        try { await AsyncStorage.multiRemove(keys.slice(i, i + CHUNK)); } catch {}
      }
    }
    await AsyncStorage.removeItem(KEYS_INDEX);
    await AsyncStorage.removeItem(MANIFEST_KEY);
  } catch {
    // ignore
  }
  await setSyncState({ ...DEFAULT_STATE, last_run: null });
}

export function pauseSync(): void {
  abort = true;
}

export async function getOfflineFootprint(): Promise<{ files: number; bytes: number }> {
  try {
    const idx = await readKeysIndex();
    if (idx.size === 0) return { files: 0, bytes: 0 };
    const keys = [...idx];
    let bytes = 0;
    let files = 0;
    // Read in chunks of 100 for performance
    const CHUNK = 100;
    for (let i = 0; i < keys.length; i += CHUNK) {
      try {
        const pairs = await AsyncStorage.multiGet(keys.slice(i, i + CHUNK));
        for (const [, v] of pairs) {
          if (v != null) {
            files++;
            // Each char ≈ 1 byte for the ASCII-leaning JSON our backend returns;
            // roughly 2x for full UTF-16 in JS strings. Use bytelen approx.
            bytes += (v as string).length;
          }
        }
      } catch {}
    }
    return { files, bytes };
  } catch {
    return { files: 0, bytes: 0 };
  }
}

/**
 * Download every chapter for every book / bible / track listed in the manifest.
 * onProgress is called periodically as state advances.
 *
 * `chaptersPerItem === Infinity` means "all chapters this item declares".
 */
export async function syncAllOffline(
  onProgress: (state: SyncState) => void,
  opts: { chaptersPerItem?: number; itemTypes?: Array<'book' | 'bible' | 'track' | 'subject'> } = {},
): Promise<SyncState> {
  abort = false;
  const chaptersPerItem = opts.chaptersPerItem ?? 5;
  const itemTypes = opts.itemTypes ?? ['book', 'bible', 'track'];

  let state = await setSyncState({
    status: 'downloading',
    error: null,
    downloaded: 0,
    errors_count: 0,
  });
  onProgress(state);

  const work: Array<{
    type: 'book' | 'bible' | 'track' | 'subject';
    id: string;
    itemKey: string;
    chapters: number;
  }> = [];

  try {
    // ── Book pages — uses `total`/row-count fallback (no `pages` field) ──
    if (itemTypes.includes('book')) {
      const limit = 50;
      let page = 1;
      let totalSeen = 0;
      while (true) {
        const r = await fetch(`${API}/api/academy/reading-library?page=${page}&limit=${limit}`);
        if (!r.ok) break;
        const data = await r.json();
        const books = data.books || [];
        if (books.length === 0) break;
        for (const b of books) {
          const total = (b.chapters || []).length || b.total_chapters || 1;
          work.push({
            type: 'book',
            id: b.id,
            itemKey: b.id,
            chapters: Math.min(total, chaptersPerItem),
          });
        }
        totalSeen += books.length;
        const declaredTotal = Number(data.total ?? data.total_count ?? 0);
        const declaredPages = Number(data.pages ?? 0);
        if (declaredPages > 0 && page >= declaredPages) break;
        if (declaredTotal > 0 && totalSeen >= declaredTotal) break;
        if (books.length < limit) break;
        page++;
        if (page > 100) break;
      }
    }
    // ── Bibles ──
    if (itemTypes.includes('bible')) {
      const limit = 50;
      let page = 1;
      let totalSeen = 0;
      while (true) {
        const r = await fetch(`${API}/api/academy/bibles?page=${page}&limit=${limit}`);
        if (!r.ok) break;
        const data = await r.json();
        const bibles = data.bibles || [];
        if (bibles.length === 0) break;
        for (const b of bibles) {
          const tot =
            (b.sections || []).reduce((n: number, s: any) => n + (s.articles?.length || 0), 0) ||
            b.total_articles ||
            1;
          work.push({
            type: 'bible',
            id: b.id,
            itemKey: `bible:${b.id}`,
            chapters: Math.min(tot, chaptersPerItem),
          });
        }
        totalSeen += bibles.length;
        const declaredTotal = Number(data.total_count ?? data.total ?? 0);
        const declaredPages = Number(data.pages ?? 0);
        if (declaredPages > 0 && page >= declaredPages) break;
        if (declaredTotal > 0 && totalSeen >= declaredTotal) break;
        if (bibles.length < limit) break;
        page++;
        if (page > 100) break;
      }
    }
    // ── Tracks ──
    if (itemTypes.includes('track')) {
      const limit = 50;
      let page = 1;
      let totalSeen = 0;
      while (true) {
        const r = await fetch(`${API}/api/academy/tracks?page=${page}&limit=${limit}`);
        if (!r.ok) break;
        const data = await r.json();
        const tracks = data.tracks || [];
        if (tracks.length === 0) break;
        for (const t of tracks) {
          const hours = Number(t.total_hours || 8);
          const total = Math.min(Math.max(Math.floor(hours / 2), 6), 12);
          work.push({
            type: 'track',
            id: t.id,
            itemKey: `track:${t.id}`,
            chapters: Math.min(total, chaptersPerItem),
          });
        }
        totalSeen += tracks.length;
        const declaredTotal = Number(data.total_count ?? data.total ?? 0);
        const declaredPages = Number(data.pages ?? 0);
        if (declaredPages > 0 && page >= declaredPages) break;
        if (declaredTotal > 0 && totalSeen >= declaredTotal) break;
        if (tracks.length < limit) break;
        page++;
        if (page > 100) break;
      }
    }

    const totalChapters = work.reduce((n, w) => n + w.chapters, 0);
    state = await setSyncState({
      total: totalChapters,
      manifest_books: work.length,
      manifest_chapters: totalChapters,
    });
    onProgress(state);

    // Persist manifest for inspection / debug
    try {
      await AsyncStorage.setItem(
        MANIFEST_KEY,
        JSON.stringify({ generated_at: new Date().toISOString(), work }),
      );
    } catch {}

    if (totalChapters === 0) {
      state = await setSyncState({
        status: 'failed',
        error:
          'Manifest empty — backend returned no books/bibles/tracks. Check network/API.',
      });
      onProgress(state);
      return state;
    }

    // Flatten (item × chapter) tasks for a 6-way concurrent worker pool
    const tasks: Array<{ w: typeof work[number]; idx: number }> = [];
    for (const w of work) {
      for (let idx = 0; idx < w.chapters; idx++) tasks.push({ w, idx });
    }

    let done = 0;
    let errors = 0;
    const CONCURRENCY = 6;
    let cursor = 0;

    // Cache existing keys once so we don't re-download things already saved
    const existing = await readKeysIndex();
    const newKeys: string[] = [];

    async function worker() {
      while (true) {
        if (abort) return;
        const i = cursor++;
        if (i >= tasks.length) return;
        const { w, idx } = tasks[i];
        const k = chapKey(w.itemKey, idx);
        try {
          if (existing.has(k)) {
            const exists = await AsyncStorage.getItem(k);
            if (exists != null) {
              done++;
              if (done % 10 === 0) {
                state = await setSyncState({ downloaded: done, errors_count: errors });
                onProgress(state);
              }
              continue;
            }
          }
          let url: string;
          if (w.type === 'book') url = `${API}/api/academy/reading-library/book/${w.id}/chapter/${idx}/content`;
          else if (w.type === 'bible') url = `${API}/api/academy/bible/${w.id}/chapter/${idx}/content`;
          else if (w.type === 'track') url = `${API}/api/academy/track/${w.id}/chapter/${idx}/content`;
          else url = `${API}/api/academy/subject/${w.id}/chapter/${idx}/content`;
          const r = await fetch(url);
          if (!r.ok) {
            errors++;
            continue;
          }
          const txt = await r.text();
          if (!txt || txt.length < 50) {
            errors++;
            continue;
          }
          await AsyncStorage.setItem(k, txt);
          newKeys.push(k);
          done++;
          if (done % 10 === 0) {
            state = await setSyncState({ downloaded: done, errors_count: errors });
            onProgress(state);
          }
        } catch {
          errors++;
        }
      }
    }

    const pool = Array.from({ length: CONCURRENCY }, () => worker());
    await Promise.all(pool);

    // Persist the updated keys index in one batch
    try {
      const merged = new Set<string>([...existing, ...newKeys]);
      await writeKeysIndex(merged);
    } catch {}

    if (abort) {
      state = await setSyncState({
        status: 'paused',
        downloaded: done,
        errors_count: errors,
      });
      onProgress(state);
      return state;
    }

    state = await setSyncState({
      status: 'completed',
      downloaded: done,
      last_run: new Date().toISOString(),
      errors_count: errors,
    });
    onProgress(state);
    return state;
  } catch (e: any) {
    state = await setSyncState({
      status: 'failed',
      error: String(e?.message || e),
    });
    onProgress(state);
    return state;
  }
}
