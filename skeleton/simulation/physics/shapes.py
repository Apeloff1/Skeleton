"""Analytic collision shapes and physically meaningful mass properties."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .errors import PhysicsValidationError
from .math3d import AABB, Mat3, Transform, Vec3


def _finite(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise PhysicsValidationError(f"{name} must be finite")
    return value


def _positive(value: float, *, name: str, allow_zero: bool = False) -> float:
    value = _finite(value, name=name)
    lower_ok = value >= 0.0 if allow_zero else value > 0.0
    if not lower_ok:
        qualifier = "non-negative" if allow_zero else "positive"
        raise PhysicsValidationError(f"{name} must be {qualifier}")
    return value


class ShapeKind(str, Enum):
    SPHERE = "sphere"
    BOX = "box"
    PLANE = "plane"
    CAPSULE = "capsule"
    CYLINDER = "cylinder"
    CONVEX_HULL = "convex_hull"


@dataclass(frozen=True, slots=True)
class MassProperties:
    mass: float
    center_of_mass: Vec3
    inertia: Mat3

    def __post_init__(self) -> None:
        if not math.isfinite(self.mass) or self.mass <= 0.0:
            raise PhysicsValidationError("mass must be finite and positive")


@runtime_checkable
class CollisionShape(Protocol):
    @property
    def kind(self) -> ShapeKind: ...

    def aabb(self, transform: Transform) -> AABB | None: ...

    def support(self, direction: Vec3, transform: Transform) -> Vec3: ...

    def mass_properties(self, density: float) -> MassProperties: ...


@dataclass(frozen=True, slots=True)
class SphereShape:
    radius: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius", _positive(self.radius, name="radius"))

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.SPHERE

    def aabb(self, transform: Transform) -> AABB:
        half = Vec3.one() * self.radius
        return AABB.from_center_half_extents(transform.position, half)

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        return transform.position + direction.normalized() * self.radius

    def mass_properties(self, density: float) -> MassProperties:
        density = _positive(density, name="density")
        volume = (4.0 / 3.0) * math.pi * self.radius**3
        mass = density * volume
        inertia = (2.0 / 5.0) * mass * self.radius**2
        return MassProperties(mass, Vec3.zero(), Mat3.diagonal(Vec3.one() * inertia))


@dataclass(frozen=True, slots=True)
class BoxShape:
    half_extents: Vec3

    def __post_init__(self) -> None:
        if self.half_extents.min_component() <= 0.0:
            raise PhysicsValidationError("box half extents must be positive")

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.BOX

    def axes(self, transform: Transform) -> tuple[Vec3, Vec3, Vec3]:
        rotation = transform.rotation.to_matrix()
        return tuple(rotation.column(i) for i in range(3))  # type: ignore[return-value]

    def aabb(self, transform: Transform) -> AABB:
        rotation = transform.rotation.to_matrix()
        hx, hy, hz = self.half_extents.to_tuple()
        world_half = Vec3(
            abs(rotation.m00) * hx + abs(rotation.m01) * hy + abs(rotation.m02) * hz,
            abs(rotation.m10) * hx + abs(rotation.m11) * hy + abs(rotation.m12) * hz,
            abs(rotation.m20) * hx + abs(rotation.m21) * hy + abs(rotation.m22) * hz,
        )
        return AABB.from_center_half_extents(transform.position, world_half)

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        local_direction = transform.inverse_transform_vector(direction)
        point = Vec3(
            self.half_extents.x if local_direction.x >= 0.0 else -self.half_extents.x,
            self.half_extents.y if local_direction.y >= 0.0 else -self.half_extents.y,
            self.half_extents.z if local_direction.z >= 0.0 else -self.half_extents.z,
        )
        return transform.transform_point(point)

    def mass_properties(self, density: float) -> MassProperties:
        density = _positive(density, name="density")
        h = self.half_extents
        volume = 8.0 * h.x * h.y * h.z
        mass = density * volume
        inertia = Vec3(
            (mass / 3.0) * (h.y * h.y + h.z * h.z),
            (mass / 3.0) * (h.x * h.x + h.z * h.z),
            (mass / 3.0) * (h.x * h.x + h.y * h.y),
        )
        return MassProperties(mass, Vec3.zero(), Mat3.diagonal(inertia))


@dataclass(frozen=True, slots=True)
class CapsuleShape:
    """Capsule aligned to local +Y/-Y with cylindrical half-height."""

    radius: float
    half_height: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "radius",
            _positive(self.radius, name="radius"),
        )
        object.__setattr__(
            self,
            "half_height",
            _positive(self.half_height, name="half_height"),
        )

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.CAPSULE

    def axis(self, transform: Transform) -> Vec3:
        return transform.transform_vector(Vec3.axis(1)).normalized()

    def segment_endpoints(self, transform: Transform) -> tuple[Vec3, Vec3]:
        axis = self.axis(transform)
        offset = axis * self.half_height
        return transform.position - offset, transform.position + offset

    def aabb(self, transform: Transform) -> AABB:
        first, second = self.segment_endpoints(transform)
        radius = Vec3.one() * self.radius
        return AABB(first.min(second) - radius, first.max(second) + radius)

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        world_direction = direction.normalized()
        axis = self.axis(transform)
        endpoint = (
            transform.position + axis * self.half_height
            if world_direction.dot(axis) >= 0.0
            else transform.position - axis * self.half_height
        )
        return endpoint + world_direction * self.radius

    def mass_properties(self, density: float) -> MassProperties:
        density = _positive(density, name="density")
        radius = self.radius
        half_height = self.half_height
        cylinder_length = 2.0 * half_height

        cylinder_volume = math.pi * radius * radius * cylinder_length
        sphere_volume = (4.0 / 3.0) * math.pi * radius**3
        cylinder_mass = density * cylinder_volume
        sphere_mass = density * sphere_volume
        mass = cylinder_mass + sphere_mass

        cylinder_axial = 0.5 * cylinder_mass * radius**2
        cylinder_transverse = (
            cylinder_mass
            * (3.0 * radius**2 + cylinder_length**2)
            / 12.0
        )

        # The two hemispheres together have sphere_mass. Each hemisphere's
        # centroid is 3r/8 beyond its flat face. 83/320 mr^2 is the transverse
        # inertia of one solid hemisphere about its own centroid.
        hemisphere_offset = half_height + 3.0 * radius / 8.0
        cap_axial = (2.0 / 5.0) * sphere_mass * radius**2
        cap_transverse = sphere_mass * (
            (83.0 / 320.0) * radius**2
            + hemisphere_offset**2
        )

        inertia = Vec3(
            cylinder_transverse + cap_transverse,
            cylinder_axial + cap_axial,
            cylinder_transverse + cap_transverse,
        )
        return MassProperties(
            mass,
            Vec3.zero(),
            Mat3.diagonal(inertia),
        )


@dataclass(frozen=True, slots=True)
class CylinderShape:
    """Finite solid cylinder aligned to local +Y/-Y."""

    radius: float
    half_height: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "radius",
            _positive(self.radius, name="radius"),
        )
        object.__setattr__(
            self,
            "half_height",
            _positive(self.half_height, name="half_height"),
        )

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.CYLINDER

    def axis(self, transform: Transform) -> Vec3:
        return transform.transform_vector(Vec3.axis(1)).normalized()

    def aabb(self, transform: Transform) -> AABB:
        axis = self.axis(transform)
        values = axis.to_tuple()
        half = Vec3(
            abs(values[0]) * self.half_height
            + self.radius * math.sqrt(max(0.0, 1.0 - values[0] ** 2)),
            abs(values[1]) * self.half_height
            + self.radius * math.sqrt(max(0.0, 1.0 - values[1] ** 2)),
            abs(values[2]) * self.half_height
            + self.radius * math.sqrt(max(0.0, 1.0 - values[2] ** 2)),
        )
        return AABB.from_center_half_extents(transform.position, half)

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        local = transform.inverse_transform_vector(direction)
        axial_sign = 1.0 if local.y >= 0.0 else -1.0
        radial_sq = local.x * local.x + local.z * local.z
        if radial_sq <= 1.0e-24:
            radial_x = 0.0
            radial_z = 0.0
        else:
            inverse = self.radius / math.sqrt(radial_sq)
            radial_x = local.x * inverse
            radial_z = local.z * inverse
        local_point = Vec3(
            radial_x,
            axial_sign * self.half_height,
            radial_z,
        )
        return transform.transform_point(local_point)

    def mass_properties(self, density: float) -> MassProperties:
        density = _positive(density, name="density")
        length = 2.0 * self.half_height
        volume = math.pi * self.radius**2 * length
        mass = density * volume
        axial = 0.5 * mass * self.radius**2
        transverse = (
            mass * (3.0 * self.radius**2 + length**2) / 12.0
        )
        return MassProperties(
            mass,
            Vec3.zero(),
            Mat3.diagonal(Vec3(transverse, axial, transverse)),
        )


@dataclass(frozen=True, slots=True)
class ConvexHullShape:
    """Closed oriented convex triangle mesh with canonical support topology.

    Vertex order is canonicalized lexically and triangle indices are remapped so
    equivalent input permutations produce identical shape state.  The mesh must
    be closed, consistently oriented, non-degenerate, and convex.
    """

    vertices: tuple[Vec3, ...]
    triangles: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        try:
            source_vertices = tuple(self.vertices)
            source_triangles = tuple(tuple(row) for row in self.triangles)
        except TypeError as exc:
            raise PhysicsValidationError(
                "convex hull vertices and triangles must be iterable"
            ) from exc

        if len(source_vertices) < 4:
            raise PhysicsValidationError(
                "convex hull requires at least four vertices"
            )
        if not all(isinstance(vertex, Vec3) for vertex in source_vertices):
            raise PhysicsValidationError(
                "convex hull vertices must be Vec3"
            )
        if len({vertex.to_tuple() for vertex in source_vertices}) != len(
            source_vertices
        ):
            raise PhysicsValidationError(
                "convex hull vertices must be unique"
            )
        if len(source_triangles) < 4:
            raise PhysicsValidationError(
                "convex hull requires at least four triangles"
            )

        order = sorted(
            range(len(source_vertices)),
            key=lambda index: (
                source_vertices[index].to_tuple(),
                index,
            ),
        )
        remap = {
            old_index: new_index
            for new_index, old_index in enumerate(order)
        }
        vertices = tuple(source_vertices[index] for index in order)

        remapped: list[tuple[int, int, int]] = []
        for triangle in source_triangles:
            if len(triangle) != 3:
                raise PhysicsValidationError(
                    "convex hull triangle must contain three indices"
                )
            if any(
                isinstance(index, bool) or not isinstance(index, int)
                for index in triangle
            ):
                raise PhysicsValidationError(
                    "convex hull triangle indices must be integers"
                )
            if any(index < 0 or index >= len(source_vertices) for index in triangle):
                raise PhysicsValidationError(
                    "convex hull triangle index outside vertex range"
                )
            mapped = tuple(remap[index] for index in triangle)
            if len(set(mapped)) != 3:
                raise PhysicsValidationError(
                    "convex hull triangle indices must be distinct"
                )
            a, b, d = (vertices[index] for index in mapped)
            if (b - a).cross(d - a).length_squared() <= 1.0e-24:
                raise PhysicsValidationError(
                    "convex hull contains degenerate triangle"
                )
            minimum_position = min(range(3), key=lambda i: mapped[i])
            canonical = (
                mapped[minimum_position],
                mapped[(minimum_position + 1) % 3],
                mapped[(minimum_position + 2) % 3],
            )
            remapped.append(canonical)

        if len(set(remapped)) != len(remapped):
            raise PhysicsValidationError(
                "convex hull triangles must be unique"
            )
        triangles = tuple(sorted(remapped))

        def validate_edges(rows: tuple[tuple[int, int, int], ...]) -> None:
            undirected: dict[tuple[int, int], int] = {}
            directed: dict[tuple[int, int], int] = {}
            for i, j, k in rows:
                for start, end in ((i, j), (j, k), (k, i)):
                    edge = tuple(sorted((start, end)))
                    undirected[edge] = undirected.get(edge, 0) + 1
                    directed[(start, end)] = directed.get((start, end), 0) + 1
            if any(count != 2 for count in undirected.values()):
                raise PhysicsValidationError(
                    "convex hull triangle mesh must be closed"
                )
            for first, second in undirected:
                if (
                    directed.get((first, second), 0) != 1
                    or directed.get((second, first), 0) != 1
                ):
                    raise PhysicsValidationError(
                        "convex hull triangle winding must be consistent"
                    )

        validate_edges(triangles)

        signed_volume = 0.0
        for i, j, k in triangles:
            a, b, d = vertices[i], vertices[j], vertices[k]
            signed_volume += a.dot(b.cross(d)) / 6.0
        if abs(signed_volume) <= 1.0e-15:
            raise PhysicsValidationError(
                "convex hull enclosed volume must be non-zero"
            )
        if signed_volume < 0.0:
            flipped: list[tuple[int, int, int]] = []
            for i, j, k in triangles:
                row = (i, k, j)
                minimum_position = min(range(3), key=lambda p: row[p])
                flipped.append(
                    (
                        row[minimum_position],
                        row[(minimum_position + 1) % 3],
                        row[(minimum_position + 2) % 3],
                    )
                )
            triangles = tuple(sorted(flipped))
            validate_edges(triangles)

        for i, j, k in triangles:
            a, b, d = vertices[i], vertices[j], vertices[k]
            normal = (b - a).cross(d - a)
            tolerance = 1.0e-9 * max(1.0, normal.length())
            if any(
                normal.dot(vertex - a) > tolerance
                for vertex in vertices
            ):
                raise PhysicsValidationError(
                    "convex hull mesh is not convex or winding is inconsistent"
                )

        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "triangles", triangles)

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.CONVEX_HULL

    def bounding_radius(self) -> float:
        return max(vertex.length() for vertex in self.vertices)

    def aabb(self, transform: Transform) -> AABB:
        transformed = tuple(
            transform.transform_point(vertex)
            for vertex in self.vertices
        )
        minimum = transformed[0]
        maximum = transformed[0]
        for point in transformed[1:]:
            minimum = minimum.min(point)
            maximum = maximum.max(point)
        return AABB(minimum, maximum)

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        local_direction = transform.inverse_transform_vector(direction)
        if local_direction.length_squared() <= 1.0e-24:
            raise PhysicsValidationError(
                "convex hull support direction must be non-zero"
            )
        index = max(
            range(len(self.vertices)),
            key=lambda item: (
                self.vertices[item].dot(local_direction),
                -item,
            ),
        )
        return transform.transform_point(self.vertices[index])

    @staticmethod
    def _second_moment_component(
        a: Vec3,
        b: Vec3,
        c: Vec3,
        volume: float,
        first_axis: int,
        second_axis: int,
    ) -> float:
        points = (a.to_tuple(), b.to_tuple(), c.to_tuple())
        diagonal = sum(
            point[first_axis] * point[second_axis]
            for point in points
        ) * (volume / 10.0)
        cross = 0.0
        for left in range(3):
            for right in range(left + 1, 3):
                cross += (
                    points[left][first_axis] * points[right][second_axis]
                    + points[right][first_axis] * points[left][second_axis]
                )
        return diagonal + cross * (volume / 20.0)

    def mass_properties(self, density: float) -> MassProperties:
        density = _positive(density, name="density")
        volume = 0.0
        first_moment = Vec3.zero()
        second = [[0.0, 0.0, 0.0] for _ in range(3)]

        for i, j, k in self.triangles:
            a, b, c = self.vertices[i], self.vertices[j], self.vertices[k]
            tetra_volume = a.dot(b.cross(c)) / 6.0
            volume += tetra_volume
            first_moment = (
                first_moment
                + (a + b + c) * (tetra_volume / 4.0)
            )
            for row in range(3):
                for column in range(3):
                    second[row][column] += self._second_moment_component(
                        a,
                        b,
                        c,
                        tetra_volume,
                        row,
                        column,
                    )

        if volume <= 1.0e-15:
            raise PhysicsValidationError(
                "convex hull mass volume must be positive"
            )

        center = first_moment / volume
        mass = density * volume
        trace = second[0][0] + second[1][1] + second[2][2]
        inertia_origin = Mat3(
            density * (trace - second[0][0]),
            -density * second[0][1],
            -density * second[0][2],
            -density * second[1][0],
            density * (trace - second[1][1]),
            -density * second[1][2],
            -density * second[2][0],
            -density * second[2][1],
            density * (trace - second[2][2]),
        )

        cx, cy, cz = center.to_tuple()
        shift = Mat3(
            mass * (cy * cy + cz * cz),
            -mass * cx * cy,
            -mass * cx * cz,
            -mass * cy * cx,
            mass * (cx * cx + cz * cz),
            -mass * cy * cz,
            -mass * cz * cx,
            -mass * cz * cy,
            mass * (cx * cx + cy * cy),
        )
        inertia = inertia_origin + (shift * -1.0)

        return MassProperties(
            mass,
            center,
            inertia,
        )


@dataclass(frozen=True, slots=True)
class PlaneShape:
    """Infinite plane using local equation normal · x = offset."""

    normal: Vec3 = Vec3(0.0, 1.0, 0.0)
    offset: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "normal", self.normal.normalized())
        object.__setattr__(self, "offset", _finite(self.offset, name="offset"))

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.PLANE

    def world_equation(self, transform: Transform) -> tuple[Vec3, float]:
        normal = transform.transform_vector(self.normal).normalized()
        return normal, self.offset + normal.dot(transform.position)

    def aabb(self, transform: Transform) -> None:
        del transform
        return None

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        del direction, transform
        raise PhysicsValidationError("an infinite plane has no finite support point")

    def mass_properties(self, density: float) -> MassProperties:
        del density
        raise PhysicsValidationError("an infinite plane cannot have finite mass properties")
