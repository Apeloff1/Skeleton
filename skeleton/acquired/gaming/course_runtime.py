"""Reusable 3D course primitives mined and evolved from HyperForge Cockpit.

HyperForge's browser runtime contains a compact gate-crossing model for flight
courses: each ring is a plane with a radius, and progress advances only when
the craft crosses that plane in the intended direction inside the aperture.

This port removes Three.js/UI dependencies, normalizes the source runtime's
crossing direction so ring normals consistently point along course travel, and
checks the actual segment/plane intersection.  The intersection check prevents
fast objects from tunnelling through a gate between simulation samples.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from skeleton.kernel.events import EventBus


@dataclass(frozen=True)
class Point3:
    x: float
    y: float
    z: float

    def lerp(self, other: "Point3", t: float) -> "Point3":
        return Point3(
            self.x + (other.x - self.x) * t,
            self.y + (other.y - self.y) * t,
            self.z + (other.z - self.z) * t,
        )


@dataclass(frozen=True)
class RingGate:
    x: float
    y: float
    z: float
    nx: float
    ny: float
    nz: float
    radius: float

    def __post_init__(self) -> None:
        if self.radius <= 0:
            raise ValueError("ring radius must be positive")
        magnitude = math.sqrt(self.nx * self.nx + self.ny * self.ny + self.nz * self.nz)
        if magnitude <= 1e-12:
            raise ValueError("ring normal cannot be zero")

    @property
    def center(self) -> Point3:
        return Point3(self.x, self.y, self.z)

    @property
    def normal(self) -> Tuple[float, float, float]:
        magnitude = math.sqrt(self.nx * self.nx + self.ny * self.ny + self.nz * self.nz)
        return self.nx / magnitude, self.ny / magnitude, self.nz / magnitude

    def signed_distance(self, point: Point3) -> float:
        nx, ny, nz = self.normal
        return (
            (point.x - self.x) * nx
            + (point.y - self.y) * ny
            + (point.z - self.z) * nz
        )


@dataclass(frozen=True)
class GateCrossing:
    crossed: bool
    t: Optional[float] = None
    radial_distance: Optional[float] = None
    intersection: Optional[Point3] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "crossed": self.crossed,
            "t": self.t,
            "radial_distance": self.radial_distance,
            "intersection": None
            if self.intersection is None
            else {
                "x": self.intersection.x,
                "y": self.intersection.y,
                "z": self.intersection.z,
            },
        }


def segment_crosses_ring(
    start: Point3,
    end: Point3,
    ring: RingGate,
    *,
    margin: float = 0.0,
) -> GateCrossing:
    """Return whether a movement segment crosses a ring forward through its aperture.

    Ring normals point in the intended direction of travel.  A valid crossing
    therefore moves from the negative half-space to the non-negative half-space.
    HyperForge's source predicate used the opposite sign transition even though
    its course builder pointed normals forward; the mined primitive resolves that
    inconsistency rather than preserving it.
    """

    margin = max(0.0, float(margin))
    d0 = ring.signed_distance(start)
    d1 = ring.signed_distance(end)
    if not (d0 < 0.0 and d1 >= 0.0):
        return GateCrossing(False)

    denominator = d1 - d0
    if denominator <= 1e-12:
        return GateCrossing(False)
    t = max(0.0, min(1.0, -d0 / denominator))
    hit = start.lerp(end, t)

    nx, ny, nz = ring.normal
    dx = hit.x - ring.x
    dy = hit.y - ring.y
    dz = hit.z - ring.z
    plane_offset = dx * nx + dy * ny + dz * nz
    rx = dx - nx * plane_offset
    ry = dy - ny * plane_offset
    rz = dz - nz * plane_offset
    radial = math.sqrt(rx * rx + ry * ry + rz * rz)
    crossed = radial <= ring.radius + margin
    return GateCrossing(
        crossed,
        round(t, 6),
        round(radial, 6),
        hit,
    )


def orient_ring_path(
    points: Sequence[Point3],
    *,
    radius: float = 7.2,
    closed: bool = False,
) -> List[RingGate]:
    """Build oriented ring gates whose normals point to the next waypoint."""

    if radius <= 0:
        raise ValueError("radius must be positive")
    if len(points) < 2:
        raise ValueError("at least two points are required")

    rings: List[RingGate] = []
    for index, point in enumerate(points):
        if index + 1 < len(points):
            target = points[index + 1]
        elif closed:
            target = points[0]
        else:
            # Preserve the final heading for an open course.
            previous = points[index - 1]
            target = Point3(
                point.x + (point.x - previous.x),
                point.y + (point.y - previous.y),
                point.z + (point.z - previous.z),
            )
        dx = target.x - point.x
        dy = target.y - point.y
        dz = target.z - point.z
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= 1e-12:
            raise ValueError(f"duplicate adjacent course points at index {index}")
        rings.append(
            RingGate(
                point.x,
                point.y,
                point.z,
                dx / length,
                dy / length,
                dz / length,
                radius,
            )
        )
    return rings


class CourseTracker:
    """Stateful ordered ring-course progress tracker."""

    def __init__(
        self,
        rings: Iterable[RingGate],
        *,
        margin: float = 1.6,
        bus: Optional[EventBus] = None,
        course_id: str = "course",
    ):
        self.rings = tuple(rings)
        if not self.rings:
            raise ValueError("course must contain at least one ring")
        self.margin = max(0.0, float(margin))
        self.bus = bus
        self.course_id = str(course_id)
        self.next_ring = 0
        self.combo = 0
        self.completed = False
        self._position: Optional[Point3] = None

    def reset(self, position: Point3) -> None:
        self.next_ring = 0
        self.combo = 0
        self.completed = False
        self._position = position
        if self.bus:
            self.bus.emit(
                "acquired.gaming.course.reset",
                {"course_id": self.course_id, "rings": len(self.rings)},
            )

    def update(self, position: Point3) -> Optional[Dict[str, Any]]:
        """Advance course state using movement from the previous position."""

        if self._position is None:
            self._position = position
            return None
        if self.completed:
            self._position = position
            return None

        ring_index = self.next_ring
        ring = self.rings[ring_index]
        crossing = segment_crosses_ring(self._position, position, ring, margin=self.margin)
        self._position = position
        if not crossing.crossed:
            return None

        self.next_ring += 1
        self.combo += 1
        self.completed = self.next_ring >= len(self.rings)
        event = {
            "course_id": self.course_id,
            "ring_index": ring_index,
            "rings_done": self.next_ring,
            "rings_total": len(self.rings),
            "combo": self.combo,
            "completed": self.completed,
            "radial_distance": crossing.radial_distance,
        }
        if self.bus:
            self.bus.emit("acquired.gaming.course.gate", event)
            if self.completed:
                self.bus.emit(
                    "acquired.gaming.course.finished",
                    {"course_id": self.course_id, "rings": len(self.rings)},
                )
        return event

    def progress(self) -> Dict[str, Any]:
        return {
            "course_id": self.course_id,
            "rings_done": self.next_ring,
            "rings_total": len(self.rings),
            "progress": round(self.next_ring / len(self.rings), 6),
            "combo": self.combo,
            "completed": self.completed,
        }


__all__ = [
    "CourseTracker",
    "GateCrossing",
    "Point3",
    "RingGate",
    "orient_ring_path",
    "segment_crosses_ring",
]
