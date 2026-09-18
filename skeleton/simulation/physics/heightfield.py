"""Deterministic grid heightfield terrain with direct cell acceleration."""
from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass, field

from .errors import PhysicsValidationError
from .math3d import AABB, Transform, Vec3
from .shapes import MassProperties, ShapeKind

MAX_HEIGHTFIELD_ROWS = 4096
MAX_HEIGHTFIELD_COLUMNS = 4096
_HEIGHT_EPSILON = 1.0e-12


@dataclass(frozen=True, slots=True)
class HeightFieldRayHit:
    triangle_index: int
    distance: float
    point: Vec3
    normal: Vec3
    barycentric: tuple[float, float, float]

    def __post_init__(self) -> None:
        if (
            isinstance(self.triangle_index, bool)
            or not isinstance(self.triangle_index, int)
            or self.triangle_index < 0
        ):
            raise PhysicsValidationError(
                "heightfield ray triangle index must be non-negative integer"
            )
        if not math.isfinite(self.distance) or self.distance < 0.0:
            raise PhysicsValidationError(
                "heightfield ray distance must be finite and non-negative"
            )
        object.__setattr__(self, "normal", self.normal.normalized())
        if len(self.barycentric) != 3:
            raise PhysicsValidationError(
                "heightfield ray barycentric must contain three weights"
            )
        if any(not math.isfinite(value) for value in self.barycentric):
            raise PhysicsValidationError(
                "heightfield ray barycentric weights must be finite"
            )


def _positive(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise PhysicsValidationError(
            f"{name} must be finite and positive"
        )
    return value


def _ray_aabb(
    origin: Vec3,
    direction: Vec3,
    bounds: AABB,
    max_distance: float,
) -> tuple[float, float] | None:
    near = 0.0
    far = max_distance
    origins = origin.to_tuple()
    directions = direction.to_tuple()
    lowers = bounds.minimum.to_tuple()
    uppers = bounds.maximum.to_tuple()

    for axis in range(3):
        component = directions[axis]
        if abs(component) <= _HEIGHT_EPSILON:
            if origins[axis] < lowers[axis] or origins[axis] > uppers[axis]:
                return None
            continue
        inverse = 1.0 / component
        first = (lowers[axis] - origins[axis]) * inverse
        second = (uppers[axis] - origins[axis]) * inverse
        if first > second:
            first, second = second, first
        near = max(near, first)
        far = min(far, second)
        if near > far:
            return None
    return near, far


@dataclass(frozen=True, slots=True)
class HeightFieldShape:
    """Regular X/Z grid with one finite height value per vertex."""

    heights: tuple[tuple[float, ...], ...]
    cell_size_x: float = 1.0
    cell_size_z: float = 1.0
    _rows: int = field(init=False, repr=False, compare=False)
    _columns: int = field(init=False, repr=False, compare=False)
    _minimum_height: float = field(init=False, repr=False, compare=False)
    _maximum_height: float = field(init=False, repr=False, compare=False)
    _local_bounds: AABB = field(init=False, repr=False, compare=False)
    _geometry_fingerprint: str = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        try:
            heights = tuple(
                tuple(float(value) for value in row)
                for row in self.heights
            )
        except (TypeError, ValueError) as exc:
            raise PhysicsValidationError(
                "heightfield heights must be numeric rows"
            ) from exc

        rows = len(heights)
        if not 2 <= rows <= MAX_HEIGHTFIELD_ROWS:
            raise PhysicsValidationError(
                "heightfield row count outside supported range"
            )
        columns = len(heights[0]) if heights else 0
        if not 2 <= columns <= MAX_HEIGHTFIELD_COLUMNS:
            raise PhysicsValidationError(
                "heightfield column count outside supported range"
            )
        if any(len(row) != columns for row in heights):
            raise PhysicsValidationError(
                "heightfield rows must have equal column count"
            )
        if any(
            not math.isfinite(value)
            for row in heights
            for value in row
        ):
            raise PhysicsValidationError(
                "heightfield heights must be finite"
            )

        cell_size_x = _positive(
            self.cell_size_x,
            name="cell_size_x",
        )
        cell_size_z = _positive(
            self.cell_size_z,
            name="cell_size_z",
        )
        minimum_height = min(min(row) for row in heights)
        maximum_height = max(max(row) for row in heights)
        local_bounds = AABB(
            Vec3(0.0, minimum_height, 0.0),
            Vec3(
                (columns - 1) * cell_size_x,
                maximum_height,
                (rows - 1) * cell_size_z,
            ),
        )

        geometry_hash = hashlib.sha256()
        geometry_hash.update(
            struct.pack(
                ">QQdd",
                rows,
                columns,
                cell_size_x,
                cell_size_z,
            )
        )
        for row in heights:
            for value in row:
                geometry_hash.update(struct.pack(">d", value))

        object.__setattr__(self, "heights", heights)
        object.__setattr__(self, "cell_size_x", cell_size_x)
        object.__setattr__(self, "cell_size_z", cell_size_z)
        object.__setattr__(self, "_rows", rows)
        object.__setattr__(self, "_columns", columns)
        object.__setattr__(self, "_minimum_height", minimum_height)
        object.__setattr__(self, "_maximum_height", maximum_height)
        object.__setattr__(self, "_local_bounds", local_bounds)
        object.__setattr__(
            self,
            "_geometry_fingerprint",
            geometry_hash.hexdigest(),
        )

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.HEIGHTFIELD

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def triangle_count(self) -> int:
        return (self.rows - 1) * (self.columns - 1) * 2

    @property
    def minimum_height(self) -> float:
        return self._minimum_height

    @property
    def maximum_height(self) -> float:
        return self._maximum_height

    @property
    def local_bounds(self) -> AABB:
        return self._local_bounds

    @property
    def geometry_fingerprint(self) -> str:
        return self._geometry_fingerprint

    def vertex(self, row: int, column: int) -> Vec3:
        if (
            isinstance(row, bool)
            or not isinstance(row, int)
            or isinstance(column, bool)
            or not isinstance(column, int)
            or not 0 <= row < self.rows
            or not 0 <= column < self.columns
        ):
            raise PhysicsValidationError(
                "heightfield vertex index out of range"
            )
        return Vec3(
            column * self.cell_size_x,
            self.heights[row][column],
            row * self.cell_size_z,
        )

    def _triangle_coordinates(
        self,
        triangle_index: int,
    ) -> tuple[int, int, int]:
        if (
            isinstance(triangle_index, bool)
            or not isinstance(triangle_index, int)
            or not 0 <= triangle_index < self.triangle_count
        ):
            raise PhysicsValidationError(
                "heightfield triangle index out of range"
            )
        cell_index = triangle_index // 2
        local_triangle = triangle_index % 2
        cell_columns = self.columns - 1
        row = cell_index // cell_columns
        column = cell_index % cell_columns
        return row, column, local_triangle

    def triangle_vertices(
        self,
        triangle_index: int,
    ) -> tuple[Vec3, Vec3, Vec3]:
        row, column, local_triangle = self._triangle_coordinates(
            triangle_index
        )
        p00 = self.vertex(row, column)
        p10 = self.vertex(row, column + 1)
        p01 = self.vertex(row + 1, column)
        p11 = self.vertex(row + 1, column + 1)
        if local_triangle == 0:
            return p00, p11, p10
        return p00, p01, p11

    def triangle_normal(self, triangle_index: int) -> Vec3:
        a, b, c = self.triangle_vertices(triangle_index)
        normal = (b - a).cross(c - a)
        if normal.length_squared() <= 1.0e-24:
            raise PhysicsValidationError(
                "heightfield contains degenerate triangle"
            )
        return normal.normalized()

    def aabb(self, transform: Transform) -> AABB:
        bounds = self.local_bounds
        center = bounds.center()
        half = bounds.half_extents()
        rotation = transform.rotation.to_matrix()
        world_center = transform.transform_point(center)
        world_half = Vec3(
            abs(rotation.m00) * half.x
            + abs(rotation.m01) * half.y
            + abs(rotation.m02) * half.z,
            abs(rotation.m10) * half.x
            + abs(rotation.m11) * half.y
            + abs(rotation.m12) * half.z,
            abs(rotation.m20) * half.x
            + abs(rotation.m21) * half.y
            + abs(rotation.m22) * half.z,
        )
        return AABB.from_center_half_extents(world_center, world_half)

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        local_direction = transform.inverse_transform_vector(direction)
        if local_direction.length_squared() <= 1.0e-24:
            raise PhysicsValidationError(
                "heightfield support direction must be non-zero"
            )
        best_row = 0
        best_column = 0
        best_dot = self.vertex(0, 0).dot(local_direction)
        for row in range(self.rows):
            for column in range(self.columns):
                value = self.vertex(row, column).dot(local_direction)
                if value > best_dot:
                    best_dot = value
                    best_row = row
                    best_column = column
        return transform.transform_point(
            self.vertex(best_row, best_column)
        )

    def mass_properties(self, density: float) -> MassProperties:
        del density
        raise PhysicsValidationError(
            "heightfields are static terrain and have no dynamic mass properties"
        )

    def candidate_triangles(self, bounds: AABB) -> tuple[int, ...]:
        if not isinstance(bounds, AABB):
            raise PhysicsValidationError(
                "heightfield candidate query requires AABB"
            )
        if not self.local_bounds.overlaps(bounds):
            return ()

        minimum_column = max(
            0,
            math.floor(bounds.minimum.x / self.cell_size_x) - 1,
        )
        maximum_column = min(
            self.columns - 2,
            math.floor(bounds.maximum.x / self.cell_size_x),
        )
        minimum_row = max(
            0,
            math.floor(bounds.minimum.z / self.cell_size_z) - 1,
        )
        maximum_row = min(
            self.rows - 2,
            math.floor(bounds.maximum.z / self.cell_size_z),
        )

        if (
            minimum_column > maximum_column
            or minimum_row > maximum_row
        ):
            return ()

        result: list[int] = []
        cell_columns = self.columns - 1
        for row in range(minimum_row, maximum_row + 1):
            for column in range(minimum_column, maximum_column + 1):
                base = (row * cell_columns + column) * 2
                result.extend((base, base + 1))
        return tuple(result)

    def raycast_local(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float,
    ) -> HeightFieldRayHit | None:
        if not isinstance(origin, Vec3) or not isinstance(direction, Vec3):
            raise PhysicsValidationError(
                "heightfield ray origin/direction must be Vec3"
            )
        direction = direction.normalized()
        if (
            isinstance(max_distance, bool)
            or not isinstance(max_distance, (int, float))
            or not math.isfinite(float(max_distance))
            or float(max_distance) < 0.0
        ):
            raise PhysicsValidationError(
                "heightfield ray max_distance must be finite and non-negative"
            )
        max_distance = float(max_distance)
        interval = _ray_aabb(
            origin,
            direction,
            self.local_bounds,
            max_distance,
        )
        if interval is None:
            return None

        near, far = interval
        first = origin + direction * near
        second = origin + direction * far
        padding = Vec3(
            self.cell_size_x * 1.0e-9,
            max(
                1.0e-9,
                abs(self.maximum_height - self.minimum_height)
                * 1.0e-9,
            ),
            self.cell_size_z * 1.0e-9,
        )
        segment_bounds = AABB(
            first.min(second) - padding,
            first.max(second) + padding,
        )
        candidates: list[HeightFieldRayHit] = []
        for triangle_index in self.candidate_triangles(segment_bounds):
            hit = self._ray_triangle(
                triangle_index,
                origin,
                direction,
                max_distance,
            )
            if hit is not None:
                candidates.append(hit)

        if not candidates:
            return None
        return min(
            candidates,
            key=lambda hit: (
                hit.distance,
                hit.triangle_index,
            ),
        )

    def _ray_triangle(
        self,
        triangle_index: int,
        origin: Vec3,
        direction: Vec3,
        max_distance: float,
    ) -> HeightFieldRayHit | None:
        a, b, c = self.triangle_vertices(triangle_index)
        edge1 = b - a
        edge2 = c - a
        p = direction.cross(edge2)
        determinant = edge1.dot(p)
        if abs(determinant) <= 1.0e-12:
            return None

        inverse = 1.0 / determinant
        tvec = origin - a
        u = tvec.dot(p) * inverse
        if u < -1.0e-10 or u > 1.0 + 1.0e-10:
            return None
        q = tvec.cross(edge1)
        v = direction.dot(q) * inverse
        if v < -1.0e-10 or u + v > 1.0 + 1.0e-10:
            return None

        distance = edge2.dot(q) * inverse
        if distance < 0.0 or distance > max_distance:
            return None
        normal = edge1.cross(edge2).normalized()
        if normal.dot(direction) > 0.0:
            normal = -normal
        return HeightFieldRayHit(
            triangle_index=triangle_index,
            distance=distance,
            point=origin + direction * distance,
            normal=normal,
            barycentric=(1.0 - u - v, u, v),
        )
