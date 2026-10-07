export type Phase = "title" | "playing" | "paused" | "crash" | "finish";

export type CourseId = "rim" | "bowl" | "spire" | "helix" | "free";

export type Medal = "none" | "bronze" | "silver" | "gold" | "sun";

export interface Actions {
  roll: number;
  pitch: number;
  flare: number;
  pausePressed: boolean;
}

export interface Thermal {
  x: number;
  z: number;
  radius: number;
  strength: number;
  ceil: number;
}

export interface RingDef {
  x: number;
  y: number;
  z: number;
  nx: number;
  ny: number;
  nz: number;
  radius: number;
}

export interface Course {
  id: CourseId;
  name: string;
  blurb: string;
  par: number;
  lockedBy?: CourseId;
  start: { x: number; y: number; z: number; yaw: number };
  rings: RingDef[];
  thermals: Thermal[];
}

export interface GhostSample {
  t: number;
  x: number;
  y: number;
  z: number;
  yaw: number;
  pitch: number;
  bank: number;
}

export interface HudState {
  phase: Phase;
  courseId: CourseId;
  courseName: string;
  time: number;
  lastTime: number;
  bestTime: number;
  speed: number;
  altitude: number;
  agl: number;
  lift: number;
  inThermal: boolean;
  ringsDone: number;
  ringsTotal: number;
  combo: number;
  medal: Medal;
  hint: string;
  nearTerrain: boolean;
  distance: number;
  maxSpeed: number;
}

export interface ControlsProbe {
  getYaw: () => number;
  getSpeed: () => number;
  getRoll: () => number;
  setSteer?: (v: number) => void;
  setKeys?: (codes: string[]) => void;
}

declare global {
  interface Window {
    __controlsTest?: ControlsProbe;
    __caldera?: {
      startCourse: (id: CourseId) => void;
      getPhase: () => Phase;
      pauseToggle: () => void;
      retry: () => void;
      toTitle: () => void;
      applySettings: () => void;
    };
  }
}
