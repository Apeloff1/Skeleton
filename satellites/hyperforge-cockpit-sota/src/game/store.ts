import { create } from "zustand";
import type { CourseId, HudState, Medal, Phase } from "./types";
import { getSave, type Settings } from "./save";

const save = getSave();

export interface GameStore extends HudState {
  settings: Settings;
  unlocked: CourseId[];
  best: Partial<Record<CourseId, number>>;
  medals: Partial<Record<CourseId, Medal>>;
  totalDistance: number;
  showSettings: boolean;
  isCoarse: boolean;
  setHud: (partial: Partial<HudState>) => void;
  setSettings: (partial: Partial<Settings>) => void;
  setMeta: (partial: Partial<Pick<GameStore, "unlocked" | "best" | "medals" | "totalDistance">>) => void;
  setShowSettings: (v: boolean) => void;
}

const idle: HudState = {
  phase: "title",
  courseId: "rim",
  courseName: "Rim Circuit",
  time: 0,
  lastTime: 0,
  bestTime: save.best.rim ?? 0,
  speed: 0,
  altitude: 0,
  agl: 0,
  lift: 0,
  inThermal: false,
  ringsDone: 0,
  ringsTotal: 0,
  combo: 0,
  medal: "none",
  hint: "",
  nearTerrain: false,
  distance: 0,
  maxSpeed: 0,
};

export const useGameStore = create<GameStore>((set) => ({
  ...idle,
  settings: save.settings,
  unlocked: save.unlocked,
  best: save.best,
  medals: save.medals,
  totalDistance: save.totalDistance,
  showSettings: false,
  isCoarse: false,
  setHud: (partial) => set(partial),
  setSettings: (partial) =>
    set((s) => ({ settings: { ...s.settings, ...partial } })),
  setMeta: (partial) => set(partial),
  setShowSettings: (v) => set({ showSettings: v }),
}));

export function setPhase(phase: Phase) {
  useGameStore.getState().setHud({ phase });
}
