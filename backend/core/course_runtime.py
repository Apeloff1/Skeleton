"""Portable checkpoint-course runtime mined from Hyperforge cockpit.

Course geometry is renderer-neutral and evaluated server-side. Rings retain
position, facing and radius; crossing is directional and ordered. This gives
playables a reusable race/checkpoint primitive independent of Three.js/Godot.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from core.terrain_field import Thermal


@dataclass(frozen=True, slots=True)
class Ring:
    x: float
    y: float
    z: float
    nx: float
    ny: float
    nz: float
    radius: float = 7.0

    def __post_init__(self) -> None:
        if self.radius <= 0:
            raise ValueError("ring radius must be positive")


@dataclass(frozen=True, slots=True)
class Spawn:
    x: float
    y: float
    z: float
    yaw: float


@dataclass(frozen=True, slots=True)
class Course:
    id: str
    name: str
    par_seconds: float
    start: Spawn
    rings: tuple[Ring, ...]
    thermals: tuple[Thermal, ...] = ()
    locked_by: str | None = None


@dataclass(slots=True)
class CourseProgress:
    course_id: str
    next_ring: int = 0
    elapsed: float = 0.0
    finished: bool = False

    @property
    def completed_rings(self) -> int:
        return self.next_ring


def _normalize(dx: float, dy: float, dz: float) -> tuple[float, float, float]:
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    return dx / length, dy / length, dz / length


def build_ring_path(points: list[tuple[float, float, float, float]], *, closed: bool) -> tuple[Ring, ...]:
    if not points:
        return ()
    rings: list[Ring] = []
    for i, (x, y, z, radius) in enumerate(points):
        if closed:
            target = points[(i + 1) % len(points)]
        else:
            target = points[min(i + 1, len(points) - 1)]
        dx, dy, dz = target[0] - x, target[1] - y, target[2] - z
        if not closed and i == len(points) - 1 and len(points) > 1:
            prev = points[i - 1]
            dx, dy, dz = x - prev[0], y - prev[1], z - prev[2]
        nx, ny, nz = _normalize(dx, dy, dz)
        rings.append(Ring(x, y, z, nx, ny, nz, radius))
    return tuple(rings)


def polar_ring(angle: float, radius: float, altitude: float, get_height: Callable[[float, float], float], ring_radius: float = 7.2) -> tuple[float, float, float, float]:
    x = math.cos(angle) * radius
    z = math.sin(angle) * radius
    return x, get_height(x, z) + altitude, z, ring_radius


def crossed_ring(previous: tuple[float, float, float], current: tuple[float, float, float], ring: Ring) -> bool:
    px, py, pz = previous
    cx, cy, cz = current
    prev_side = (px - ring.x) * ring.nx + (py - ring.y) * ring.ny + (pz - ring.z) * ring.nz
    cur_side = (cx - ring.x) * ring.nx + (cy - ring.y) * ring.ny + (cz - ring.z) * ring.nz
    # Require forward passage through the ring plane, not proximity alone.
    if prev_side > 0 or cur_side < 0:
        return False
    denom = cur_side - prev_side
    t = 0.0 if abs(denom) < 1e-9 else -prev_side / denom
    t = max(0.0, min(1.0, t))
    ix = px + (cx - px) * t
    iy = py + (cy - py) * t
    iz = pz + (cz - pz) * t
    # Distance to ring center in the plane.
    rx, ry, rz = ix - ring.x, iy - ring.y, iz - ring.z
    normal_component = rx * ring.nx + ry * ring.ny + rz * ring.nz
    planar_sq = rx * rx + ry * ry + rz * rz - normal_component * normal_component
    return planar_sq <= ring.radius * ring.radius


class CourseTracker:
    def __init__(self, course: Course) -> None:
        self.course = course
        self.progress = CourseProgress(course.id)

    def step(self, dt: float, previous: tuple[float, float, float], current: tuple[float, float, float]) -> CourseProgress:
        if dt < 0:
            raise ValueError("dt cannot be negative")
        if self.progress.finished:
            return self.progress
        self.progress.elapsed += dt
        if not self.course.rings:
            return self.progress
        idx = self.progress.next_ring
        if idx < len(self.course.rings) and crossed_ring(previous, current, self.course.rings[idx]):
            self.progress.next_ring += 1
            if self.progress.next_ring >= len(self.course.rings):
                self.progress.finished = True
        return self.progress

    def medal_band(self) -> str:
        if not self.progress.finished or self.course.par_seconds <= 0:
            return "none"
        ratio = self.progress.elapsed / self.course.par_seconds
        if ratio <= 0.82:
            return "elite"
        if ratio <= 1.0:
            return "gold"
        if ratio <= 1.18:
            return "silver"
        if ratio <= 1.4:
            return "bronze"
        return "none"
