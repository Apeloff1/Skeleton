import type { CourseId, GhostSample, Medal } from "./types";

const KEY = "caldera-save";
const VERSION = 1;

export interface Settings {
  muted: boolean;
  master: number;
  shake: boolean;
  bloom: boolean;
}

export interface SaveData {
  version: number;
  best: Partial<Record<CourseId, number>>;
  medals: Partial<Record<CourseId, Medal>>;
  ghosts: Partial<Record<CourseId, GhostSample[]>>;
  settings: Settings;
  seenHint: boolean;
  totalDistance: number;
  unlocked: CourseId[];
}

const defaultSettings: Settings = {
  muted: false,
  master: 0.72,
  shake: true,
  bloom: true,
};

const defaultSave: SaveData = {
  version: VERSION,
  best: {},
  medals: {},
  ghosts: {},
  settings: { ...defaultSettings },
  seenHint: false,
  totalDistance: 0,
  unlocked: ["rim", "free"],
};

function migrate(raw: SaveData): SaveData {
  const s: SaveData = {
    ...defaultSave,
    ...raw,
    settings: { ...defaultSettings, ...(raw.settings ?? {}) },
    best: { ...raw.best },
    medals: { ...raw.medals },
    ghosts: { ...raw.ghosts },
    unlocked: raw.unlocked?.length ? raw.unlocked : ["rim", "free"],
    version: VERSION,
  };
  return s;
}

export function loadSave(): SaveData {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return structuredClone(defaultSave);
    const parsed = JSON.parse(raw) as SaveData;
    return migrate(parsed);
  } catch {
    return structuredClone(defaultSave);
  }
}

export function writeSave(data: SaveData) {
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
  } catch {
    /* private mode / quota */
  }
}

let cache = loadSave();

export function getSave() {
  return cache;
}

export function patchSave(partial: Partial<SaveData>) {
  cache = { ...cache, ...partial, settings: { ...cache.settings, ...(partial.settings ?? {}) } };
  writeSave(cache);
  return cache;
}

export function recordFinish(
  id: CourseId,
  time: number,
  medal: Medal,
  ghost: GhostSample[],
  distance: number,
) {
  const prev = cache.best[id];
  const improved = prev == null || time < prev;
  const medalsRank = { none: 0, bronze: 1, silver: 2, gold: 3, sun: 4 };
  const betterMedal = medalsRank[medal] > medalsRank[cache.medals[id] ?? "none"];
  const unlocked = new Set(cache.unlocked);
  if (medal !== "none") {
    if (id === "rim") unlocked.add("bowl");
    if (id === "bowl") unlocked.add("spire");
    if (id === "spire") unlocked.add("helix");
  }
  cache = {
    ...cache,
    best: improved ? { ...cache.best, [id]: time } : cache.best,
    medals: betterMedal ? { ...cache.medals, [id]: medal } : cache.medals,
    ghosts: improved ? { ...cache.ghosts, [id]: ghost } : cache.ghosts,
    totalDistance: cache.totalDistance + distance,
    unlocked: [...unlocked],
  };
  writeSave(cache);
  return { improved, save: cache };
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") writeSave(cache);
  });
}
