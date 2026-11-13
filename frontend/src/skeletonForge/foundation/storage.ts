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

export async function loadFoundation(store: Kv): Promise<LoadResult> {
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
      const parsed = JSON.parse(projectsRaw) as unknown;
      const result = sanitizeProjects(parsed);
      projects = result.projects;
      projectsCorrupt = result.corrupt;
    } catch {
      projectsCorrupt = true;
    }
  }
  let prefs: StudioPrefs = DEFAULT_PREFS;
  if (prefsRaw) {
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

export function saveFoundation(store: Kv, snap: PersistSnapshot): Promise<void> {
  if (snap.holdSaves || snap.projectsCorrupt) return Promise.resolve();
  // Capture the value at call time, not after another edit to the reducer.
  const onboarded = snap.onboarded ? '1' : '0';
  const projects = JSON.stringify(snap.projects);
  const prefs = JSON.stringify(snap.prefs);
  const previous = saveTails.get(store) ?? Promise.resolve();
  // A failed earlier save must surface to its caller but must NOT permanently
  // poison the queue for a subsequent explicit retry.
  const job = previous.catch(() => {}).then(async () => {
    await store.setItem(KEYS.onboarded, onboarded);
    await store.setItem(KEYS.projects, projects);
    await store.setItem(KEYS.prefs, prefs);
  });
  saveTails.set(store, job);
  void job.then(() => {
    if (saveTails.get(store) === job) saveTails.delete(store);
  }, () => {
    if (saveTails.get(store) === job) saveTails.delete(store);
  });
  return job;
}
