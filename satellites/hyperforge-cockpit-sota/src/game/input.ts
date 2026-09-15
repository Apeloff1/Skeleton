import type { Actions } from "./types";
import { clamp } from "./noise";

const GAME_KEYS = new Set([
  "KeyW",
  "KeyA",
  "KeyS",
  "KeyD",
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "Space",
  "KeyP",
  "Escape",
  "KeyR",
]);

function radialDeadzone(x: number, y: number, dz = 0.16) {
  const m = Math.hypot(x, y);
  if (m < dz) return { x: 0, y: 0 };
  const scale = ((m - dz) / (1 - dz)) / m;
  return { x: x * scale, y: y * scale };
}

export class Input {
  keys = new Set<string>();
  injected = new Set<string>();
  steerInject: number | null = null;
  touchRoll = 0;
  touchPitch = 0;
  touchFlare = false;
  private prevPause = false;
  private onKeyDown: (e: KeyboardEvent) => void;
  private onKeyUp: (e: KeyboardEvent) => void;
  private onBlur: () => void;

  constructor() {
    this.onKeyDown = (e) => {
      if (e.repeat) {
        if (GAME_KEYS.has(e.code)) e.preventDefault();
        return;
      }
      this.keys.add(e.code);
      if (GAME_KEYS.has(e.code)) e.preventDefault();
    };
    this.onKeyUp = (e) => {
      this.keys.delete(e.code);
    };
    this.onBlur = () => {
      this.keys.clear();
    };
    window.addEventListener("keydown", this.onKeyDown);
    window.addEventListener("keyup", this.onKeyUp);
    window.addEventListener("blur", this.onBlur);
    document.addEventListener("visibilitychange", this.onBlur);
  }

  setTouch(roll: number, pitch: number, flare: boolean) {
    this.touchRoll = clamp(roll, -1, 1);
    this.touchPitch = clamp(pitch, -1, 1);
    this.touchFlare = flare;
  }

  setSteer(v: number) {
    this.steerInject = v;
  }

  setKeys(codes: string[]) {
    this.injected = new Set(codes);
  }

  sample(): Actions {
    const keys = this.keys.size ? this.keys : this.injected;
    let roll = 0;
    let pitch = 0;
    if (keys.has("KeyA") || keys.has("ArrowLeft")) roll += 1;
    if (keys.has("KeyD") || keys.has("ArrowRight")) roll -= 1;
    if (keys.has("KeyW") || keys.has("ArrowUp")) pitch += 1;
    if (keys.has("KeyS") || keys.has("ArrowDown")) pitch -= 1;

    roll += this.touchRoll;
    pitch += this.touchPitch;

    const pads = navigator.getGamepads?.() ?? [];
    for (const pad of pads) {
      if (!pad) continue;
      const stick = radialDeadzone(pad.axes[0] ?? 0, pad.axes[1] ?? 0);
      roll += -stick.x;
      pitch += -stick.y;
      if (pad.buttons[0]?.pressed || pad.buttons[7]?.pressed || pad.buttons[6]?.pressed) {
        this.touchFlare = true;
      }
      if (pad.buttons[9]?.pressed) keys.add("Escape");
    }

    if (this.steerInject != null) roll = this.steerInject;

    roll = clamp(roll, -1, 1);
    pitch = clamp(pitch, -1, 1);

    const pauseHeld = keys.has("Escape") || keys.has("KeyP");
    const pausePressed = pauseHeld && !this.prevPause;
    this.prevPause = pauseHeld;

    const flare =
      keys.has("Space") || this.touchFlare ? 1 : 0;

    return { roll, pitch, flare, pausePressed };
  }

  dispose() {
    window.removeEventListener("keydown", this.onKeyDown);
    window.removeEventListener("keyup", this.onKeyUp);
    window.removeEventListener("blur", this.onBlur);
    document.removeEventListener("visibilitychange", this.onBlur);
  }
}
