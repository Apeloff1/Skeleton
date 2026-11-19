"""Deterministic spatial-hash broadphase over AABBs.

Cells are visited in sorted integer coordinates. A pair that straddles several
cells is emitted once. The hash does not use randomness or the wall clock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from skeleton.frontier_contact.bodies import AABB, BoxBody, SphereBody
from skeleton.frontier_contact.errors import ContactRejected

_MAX_CELL_SPAN = 10_000


@dataclass(frozen=True)
class BoundVolume:
    body_id: str
    kind: str
    index: int
    aabb: AABB


def _cell_size(cell_size_m: float) -> float:
    if isinstance(cell_size_m, bool) or not isinstance(cell_size_m, (int, float)):
        raise ContactRejected("cell size must be a real number")
    size = float(cell_size_m)
    if math.isnan(size):
        raise ContactRejected("NaN")
    if not math.isfinite(size) or size <= 0.0 or size > 1e6:
        raise ContactRejected("cell size out of range")
    return size


def _cell(value: float, size: float) -> int:
    return math.floor(value / size)


def overlapping_pairs(
    bounds: tuple[AABB, ...] | list[AABB],
    *,
    cell_size_m: float = 1.0,
) -> tuple[tuple[int, int], ...]:
    """Return sorted index pairs whose AABBs can overlap.

    Insertion order does not matter. The result is sorted by ``(min, max)``.
    """
    size = _cell_size(cell_size_m)
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for index, box in enumerate(bounds):
        if not isinstance(box, AABB):
            raise ContactRejected("aabb required")
        ix0 = _cell(box.minimum[0], size)
        iy0 = _cell(box.minimum[1], size)
        iz0 = _cell(box.minimum[2], size)
        ix1 = _cell(box.maximum[0], size)
        iy1 = _cell(box.maximum[1], size)
        iz1 = _cell(box.maximum[2], size)
        if max(ix1 - ix0, iy1 - iy0, iz1 - iz0) > _MAX_CELL_SPAN:
            raise ContactRejected("broadphase cell span exceeded")
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                for iz in range(iz0, iz1 + 1):
                    buckets.setdefault((ix, iy, iz), []).append(index)
    pairs: set[tuple[int, int]] = set()
    for key in sorted(buckets):
        occupants = buckets[key]
        for left in range(len(occupants)):
            for right in range(left + 1, len(occupants)):
                first = occupants[left]
                second = occupants[right]
                if first == second:
                    continue
                pairs.add((first, second) if first < second else (second, first))
    return tuple(sorted(pairs))


def _span(start: float, end: float, padding: float) -> tuple[float, float]:
    return min(start, end) - padding, max(start, end) + padding


def swept_bounds(
    spheres: tuple[SphereBody, ...] | list[SphereBody],
    boxes: tuple[BoxBody, ...] | list[BoxBody],
    dt: float,
) -> tuple[AABB, ...]:
    """Bounds of the current pose expanded by linear motion over ``dt``.

    Call this immediately before a broadphase query. Terrain half extents and
    centers are read here, so a deformation or a move is visible to the hash.
    """
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        raise ContactRejected("dt must be a real number")
    step = float(dt)
    if math.isnan(step):
        raise ContactRejected("NaN")
    if step < 0.0 or not math.isfinite(step):
        raise ContactRejected("dt out of range")
    built: list[AABB] = []
    for sphere in spheres:
        if not isinstance(sphere, SphereBody):
            raise ContactRejected("sphere required")
        low_x, high_x = _span(
            sphere.position[0],
            sphere.position[0] + sphere.velocity[0] * step,
            sphere.radius_m,
        )
        low_y, high_y = _span(
            sphere.position[1],
            sphere.position[1] + sphere.velocity[1] * step,
            sphere.radius_m,
        )
        low_z, high_z = _span(
            sphere.position[2],
            sphere.position[2] + sphere.velocity[2] * step,
            sphere.radius_m,
        )
        built.append(AABB((low_x, low_y, low_z), (high_x, high_y, high_z)))
    for box in boxes:
        if not isinstance(box, BoxBody):
            raise ContactRejected("box required")
        end = tuple(box.center[axis] + box.velocity[axis] * step for axis in range(3))
        low = tuple(
            min(box.center[axis], end[axis]) - box.half_extents[axis]
            for axis in range(3)
        )
        high = tuple(
            max(box.center[axis], end[axis]) + box.half_extents[axis]
            for axis in range(3)
        )
        built.append(AABB(low, high))
    return tuple(built)


def broadphase_volumes(
    spheres: tuple[SphereBody, ...],
    boxes: tuple[BoxBody, ...],
    dt: float,
    *,
    cell_size_m: float = 1.0,
) -> tuple[tuple[BoundVolume, ...], tuple[tuple[int, int], ...]]:
    """Hash the swept bounds and drop terrain-terrain pairs."""
    bounds = swept_bounds(spheres, boxes, dt)
    volumes: list[BoundVolume] = []
    for index, sphere in enumerate(spheres):
        volumes.append(BoundVolume(sphere.body_id, "sphere", index, bounds[index]))
    offset = len(spheres)
    for index, box in enumerate(boxes):
        volumes.append(BoundVolume(box.body_id, "box", index, bounds[offset + index]))
    pairs = []
    for left, right in overlapping_pairs(bounds, cell_size_m=cell_size_m):
        if volumes[left].kind == "box" and volumes[right].kind == "box":
            continue
        pairs.append((left, right))
    return tuple(volumes), tuple(pairs)
