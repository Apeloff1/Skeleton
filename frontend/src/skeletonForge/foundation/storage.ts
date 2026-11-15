/**
 * Device persistence for the studio shell. The store is injected so tests
 * never touch AsyncStorage, and a save is refused while a previous read
 * was unreadable.
 */
import {
  DEFAULT_PREFS, sanitizePrefs, sanitizeProjects,
  type LoadResult, type PersistSnapshot, type StudioPrefs, type StudioProject,
} from './model';

export const KEYS = {
  onboarded: 'skeleton.studio.onboarded.v1',
  projects: 'skeleton.studio.projects.v1',
  prefs: 'skeleton.studio.prefs.v1',
} as const;

export interface Kv {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  /** Optional namespace-wide queue provided by the device adapter. */
  runExclusive?<T>(task: () => Promise<T>, mode: 'read' | 'write' | 'refresh'): Promise<T>;
}

export function memoryKv(seed: Record<string, string> = {}): Kv & { dump(): Record<string, string> } {
  const data: Record<string, string> = { ...seed };
  return {
    async getItem(key) {
      return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null;
    },
    async setItem(key, value) {
      data[key] = value;
    },
    dump() {
      return { ...data };
    },
  };
}

// Storage admission limits count UTF-16 code units (AsyncStorage strings).
// Large libraries remain supported, but one corrupt blob cannot force an
// arbitrarily large JSON parse or an unbounded project-by-project traversal.
export const MAX_STUDIO_PROJECTS = 10_000;
export const MAX_STUDIO_PROJECT_CHARS = 64 * 1024 * 1024;
export const MAX_STUDIO_PREFS_CHARS = 4096;

async function readFoundation(store: Kv): Promise<LoadResult> {
  const [onboardedRaw, projectsRaw, prefsRaw] = await Promise.all([
    store.getItem(KEYS.onboarded),
    store.getItem(KEYS.projects),
    store.getItem(KEYS.prefs),
  ]);
  const onboarded = onboardedRaw === '1';
  let projects: StudioProject[] = [];
  let projectsCorrupt = false;
  if (projectsRaw != null && projectsRaw !== '') {
    try {
      if (projectsRaw.length > MAX_STUDIO_PROJECT_CHARS) throw new Error('Studio project library exceeds admission budget');
      const parsed = JSON.parse(projectsRaw) as unknown;
      if (!Array.isArray(parsed) || parsed.length > MAX_STUDIO_PROJECTS) throw new Error('Invalid Studio project library');
      const result = sanitizeProjects(parsed);
      projects = result.projects;
      projectsCorrupt = result.corrupt;
    } catch {
      projectsCorrupt = true;
    }
  }
  let prefs: StudioPrefs = DEFAULT_PREFS;
  if (prefsRaw && prefsRaw.length <= MAX_STUDIO_PREFS_CHARS) {
    try { prefs = sanitizePrefs(JSON.parse(prefsRaw) as unknown); } catch { prefs = DEFAULT_PREFS; }
  }
  const holdSaves = projectsCorrupt;
  return {
    onboarded,
    projects,
    prefs,
    projectsCorrupt,
    holdSaves,
    error: projectsCorrupt ? 'Saved projects could not be read on this device.' : null,
  };
}

// A Studio shell can enqueue several saves while the user is adjusting
// knobs, creating scenes or switching panels. AsyncStorage resolves writes
// asynchronously and does NOT guarantee later calls complete last. Serial
// saves per injected store: the newest submitted complete snapshot wins.
const saveTails = new WeakMap<Kv, Promise<void>>();

function enqueue<T>(store: Kv, task: () => Promise<T>, mode: 'read' | 'write' | 'refresh'): Promise<T> {
  if (store.runExclusive) return store.runExclusive(task, mode);
  const previous = saveTails.get(store) ?? Promise.resolve();
  const job = previous.catch(() => {}).then(task);
  const completion = job.then(() => {}, () => {});
  saveTails.set(store, completion);
  void completion.then(() => {
    if (saveTails.get(store) === completion) saveTails.delete(store);
  });
  return job;
}

export function loadFoundation(store: Kv): Promise<LoadResult> {
  return enqueue(store, () => readFoundation(store), 'read');
}

function encodeSnapshot(snap: PersistSnapshot) {
  if (!Array.isArray(snap.projects) || snap.projects.length > MAX_STUDIO_PROJECTS) {
    throw new Error('Studio project count exceeds storage admission budget');
  }
  const parts: string[] = [];
  let size = 2;
  for (const project of snap.projects) {
    const encoded = JSON.stringify(project);
    if (typeof encoded !== 'string') throw new Error('Invalid Studio project snapshot');
    size += encoded.length + (parts.length ? 1 : 0);
    if (size > MAX_STUDIO_PROJECT_CHARS) throw new Error('Studio project library exceeds storage admission budget');
    parts.push(encoded);
  }
  const prefs = JSON.stringify(snap.prefs);
  if (prefs.length > MAX_STUDIO_PREFS_CHARS) throw new Error('Studio preferences exceed storage admission budget');
  return { onboarded: snap.onboarded ? '1' : '0', projects: '[' + parts.join(',') + ']', prefs };
}

async function publish(store: Kv, encoded: ReturnType<typeof encodeSnapshot>): Promise<void> {
  // Project data is the final write, so failures in preference/onboarding
  // persistence cannot acknowledge a returning Forge project.
  await store.setItem(KEYS.prefs, encoded.prefs);
  await store.setItem(KEYS.onboarded, encoded.onboarded);
  await store.setItem(KEYS.projects, encoded.projects);
}

export function saveFoundation(store: Kv, snap: PersistSnapshot): Promise<void> {
  if (snap.holdSaves || snap.projectsCorrupt) return Promise.resolve();
  // Capture ownership-independent content at submission, before another edit.
  try {
    const encoded = encodeSnapshot(snap);
    return enqueue(store, () => publish(store, encoded), 'write');
  } catch (error) {
    return Promise.reject(error);
  }
}

/** One read/modify/publish transaction per injected store in this JS runtime.
 * A failed callback or corrupt input does not publish or poison the queue.
 * This is not a cross-process lock or distributed CAS.
 */
export function updateFoundation<T>(
  store: Kv, update: (current: LoadResult) => { snapshot: PersistSnapshot; result: T },
): Promise<T> {
  return enqueue(store, async () => {
    const current = await readFoundation(store);
    if (current.holdSaves || current.projectsCorrupt) throw new Error('Studio project library is held for recovery');
    const { snapshot, result } = update(current);
    if (snapshot.holdSaves || snapshot.projectsCorrupt) throw new Error('Studio return snapshot is held');
    await publish(store, encodeSnapshot(snapshot));
    return result;
  }, 'refresh');
}
