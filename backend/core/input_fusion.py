"""Renderer-neutral input fusion mined from Hyperforge's keyboard/touch/gamepad layer."""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def radial_deadzone(x: float, y: float, deadzone: float = 0.16) -> tuple[float, float]:
    if not 0 <= deadzone < 1:
        raise ValueError("deadzone must be in [0, 1)")
    magnitude = hypot(x, y)
    if magnitude < deadzone or magnitude == 0:
        return 0.0, 0.0
    scale = ((magnitude - deadzone) / (1 - deadzone)) / magnitude
    return clamp(x * scale), clamp(y * scale)


@dataclass(frozen=True, slots=True)
class InputSample:
    roll: float = 0.0
    pitch: float = 0.0
    flare: float = 0.0
    pause_pressed: bool = False


class InputFusion:
    """Combines digital, touch, gamepad and injected steering deterministically."""

    def __init__(self, *, deadzone: float = 0.16) -> None:
        self.deadzone = deadzone
        self._pause_held = False

    def sample(
        self,
        *,
        keys: set[str] | None = None,
        touch_roll: float = 0.0,
        touch_pitch: float = 0.0,
        touch_flare: bool = False,
        gamepad_axes: tuple[float, float] | None = None,
        gamepad_flare: bool = False,
        steer_override: float | None = None,
    ) -> InputSample:
        keys = keys or set()
        roll = 0.0
        pitch = 0.0
        if {"KeyA", "ArrowLeft"} & keys:
            roll += 1.0
        if {"KeyD", "ArrowRight"} & keys:
            roll -= 1.0
        if {"KeyW", "ArrowUp"} & keys:
            pitch += 1.0
        if {"KeyS", "ArrowDown"} & keys:
            pitch -= 1.0

        roll += clamp(touch_roll)
        pitch += clamp(touch_pitch)
        if gamepad_axes is not None:
            gx, gy = radial_deadzone(*gamepad_axes, self.deadzone)
            roll += -gx
            pitch += -gy
        if steer_override is not None:
            roll = steer_override

        pause_held = bool({"Escape", "KeyP"} & keys)
        pause_pressed = pause_held and not self._pause_held
        self._pause_held = pause_held
        flare = 1.0 if touch_flare or gamepad_flare or "Space" in keys else 0.0
        return InputSample(clamp(roll), clamp(pitch), flare, pause_pressed)
