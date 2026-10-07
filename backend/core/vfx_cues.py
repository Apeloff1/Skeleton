"""Renderer-neutral visual-effect state mined from Hyperforge VFX behavior."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, sin


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True, slots=True)
class ShakeOffset:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class BurstEvent:
    x: float
    y: float
    z: float
    count: int = 28
    intensity: float = 1.0


@dataclass(slots=True)
class VfxState:
    trauma: float = 0.0
    time: float = 0.0
    trail_limit: int = 48
    trail: list[tuple[float, float, float]] = field(default_factory=list)
    bursts: list[BurstEvent] = field(default_factory=list)

    def add_trauma(self, value: float) -> float:
        self.trauma = _clamp(self.trauma + value)
        return self.trauma

    def emit_burst(self, x: float, y: float, z: float, *, count: int = 28, intensity: float = 1.0) -> BurstEvent:
        if count <= 0:
            raise ValueError("count must be positive")
        event = BurstEvent(x, y, z, count=count, intensity=_clamp(intensity))
        self.bursts.append(event)
        return event

    def push_trail(self, x: float, y: float, z: float) -> None:
        self.trail.append((x, y, z))
        if len(self.trail) > self.trail_limit:
            del self.trail[: len(self.trail) - self.trail_limit]

    def reset_trail(self) -> None:
        self.trail.clear()

    def step(self, dt: float) -> None:
        if dt < 0:
            raise ValueError("dt cannot be negative")
        self.time += dt
        self.trauma = max(0.0, self.trauma - dt * 1.6)

    def shake_offset(self, *, reduced_motion: bool = False) -> ShakeOffset:
        if reduced_motion or self.trauma <= 0.001:
            return ShakeOffset(0.0, 0.0, 0.0)
        strength = self.trauma * self.trauma
        t = self.time * 28.0
        return ShakeOffset(
            sin(t * 1.7) * strength * 0.55,
            cos(t * 1.3) * strength * 0.40,
            sin(t * 2.1) * strength * 0.35,
        )

    @staticmethod
    def speed_streak_intensity(speed: float, *, playing: bool = True) -> float:
        if not playing or speed <= 48.0:
            return 0.0
        return _clamp((speed - 48.0) / 54.0)
