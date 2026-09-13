"""Deterministic procedural terrain and thermal fields mined from Hyperforge.

Rendering code is intentionally excluded. The retained primitives provide a
portable height field, bilinear sampling, and thermal lift evaluation that can
feed Godot, browser previews, AI agents, and server-side validation.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 0.0
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hash_noise(x: float, z: float, seed: int) -> float:
    xi = math.floor(x)
    zi = math.floor(z)
    n = (xi * 374761393 + zi * 668265263 + seed * 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
    n ^= n >> 13
    n = (n * 1274126177) & 0xFFFFFFFFFFFFFFFF
    return ((n & 0xFFFFFFFF) / 0x7FFFFFFF) - 1.0


def value_noise(x: float, z: float, seed: int = 1) -> float:
    x0 = math.floor(x)
    z0 = math.floor(z)
    tx = x - x0
    tz = z - z0
    sx = tx * tx * (3 - 2 * tx)
    sz = tz * tz * (3 - 2 * tz)
    a = _hash_noise(x0, z0, seed)
    b = _hash_noise(x0 + 1, z0, seed)
    c = _hash_noise(x0, z0 + 1, seed)
    d = _hash_noise(x0 + 1, z0 + 1, seed)
    ab = a * (1 - sx) + b * sx
    cd = c * (1 - sx) + d * sx
    return ab * (1 - sz) + cd * sz


def fbm(x: float, z: float, octaves: int, seed: int = 1) -> float:
    total = 0.0
    amp = 0.5
    freq = 1.0
    norm = 0.0
    for i in range(max(1, octaves)):
        total += value_noise(x * freq, z * freq, seed + i * 101) * amp
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm if norm else 0.0


@dataclass(frozen=True, slots=True)
class TerrainConfig:
    world_size: float = 720.0
    lava_radius: float = 58.0
    rim_radius: float = 190.0


def terrain_height(x: float, z: float, cfg: TerrainConfig = TerrainConfig()) -> float:
    r = math.hypot(x, z)
    if r < cfg.lava_radius - 2:
        return -16.0
    from_lava = smoothstep(cfg.lava_radius - 2, cfg.lava_radius + 16, r)
    bowl = -10.0 + from_lava * 10.0
    rim = (
        math.exp(-((r - cfg.rim_radius) ** 2) / (2 * 40 * 40)) * 64.0
        + math.exp(-((r - (cfg.rim_radius + 18)) ** 2) / (2 * 22 * 22)) * 18.0
    )
    outer = smoothstep(cfg.rim_radius + 40, 360, r) * 10.0
    drop = (r - 270) * 0.05 if r > 270 else 0.0
    mask = smoothstep(cfg.lava_radius + 6, cfg.lava_radius + 26, r)
    n = fbm(x * 0.016, z * 0.016, 5, 1) * 11.0 + fbm(x * 0.045, z * 0.045, 3, 7) * 3.4
    ang = math.atan2(z, x)
    ridges = (
        math.sin(ang * 7.0 + fbm(x * 0.01, z * 0.01, 2, 3) * 1.4)
        * 5.5
        * smoothstep(90, 175, r)
        * (1 - smoothstep(230, 290, r))
    )
    vent = (
        math.exp(-((x - 86) ** 2 + (z + 40) ** 2) / (2 * 28 * 28)) * 22.0
        + math.exp(-((x + 120) ** 2 + (z - 70) ** 2) / (2 * 24 * 24)) * 16.0
    )
    return bowl + rim + outer - drop + n * mask + ridges + vent * mask


class HeightField:
    def __init__(self, size: float, resolution: int, *, config: TerrainConfig = TerrainConfig()) -> None:
        if size <= 0 or resolution < 2:
            raise ValueError("size must be positive and resolution >= 2")
        self.size = size
        self.resolution = resolution
        self.config = config
        half = size / 2.0
        self.data = [0.0] * (resolution * resolution)
        for zi in range(resolution):
            for xi in range(resolution):
                wx = (xi / (resolution - 1)) * size - half
                wz = (zi / (resolution - 1)) * size - half
                self.data[zi * resolution + xi] = terrain_height(wx, wz, config)

    def sample(self, x: float, z: float) -> float:
        half = self.size / 2.0
        u = ((x + half) / self.size) * (self.resolution - 1)
        v = ((z + half) / self.size) * (self.resolution - 1)
        x0 = max(0, min(self.resolution - 2, math.floor(u)))
        z0 = max(0, min(self.resolution - 2, math.floor(v)))
        tx = clamp(u - x0, 0.0, 1.0)
        tz = clamp(v - z0, 0.0, 1.0)
        i = z0 * self.resolution + x0
        a = self.data[i]
        b = self.data[i + 1]
        c = self.data[i + self.resolution]
        d = self.data[i + self.resolution + 1]
        return a * (1 - tx) * (1 - tz) + b * tx * (1 - tz) + c * (1 - tx) * tz + d * tx * tz


@dataclass(frozen=True, slots=True)
class Thermal:
    x: float
    z: float
    radius: float
    strength: float
    ceiling: float

    def __post_init__(self) -> None:
        if self.radius <= 0 or self.strength < 0 or self.ceiling <= 0:
            raise ValueError("thermal radius/ceiling must be positive and strength non-negative")


def thermal_lift(x: float, y: float, z: float, thermals: list[Thermal]) -> float:
    lift = 0.0
    for thermal in thermals:
        if y > thermal.ceiling:
            continue
        d = math.hypot(x - thermal.x, z - thermal.z)
        if d >= thermal.radius:
            continue
        radial = 1.0 - d / thermal.radius
        height_fade = 1.0 - clamp(y / thermal.ceiling, 0.0, 1.0) * 0.35
        lift = max(lift, radial * radial * thermal.strength * height_fade)
    return lift


def seeded_thermals(count: int, *, seed: int = 1, radius: float = 180.0) -> list[Thermal]:
    if count < 0:
        raise ValueError("count cannot be negative")
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        angle = rng.random() * math.tau
        r = 70.0 + rng.random() * radius
        out.append(
            Thermal(
                x=math.cos(angle) * r,
                z=math.sin(angle) * r,
                radius=20.0 + rng.random() * 28.0,
                strength=8.0 + rng.random() * 16.0,
                ceiling=90.0 + rng.random() * 90.0,
            )
        )
    return out
