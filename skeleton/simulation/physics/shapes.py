"""Analytic collision shapes and physically meaningful mass properties."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .errors import PhysicsValidationError
from .math3d import AABB, Mat3, Transform, Vec3

MAX_CONVEX_HULL_VERTICES = 4_096
MAX_CONVEX_HULL_FACES = 8_192


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

        def world_extent(component: float) -> float:
            component = max(-1.0, min(1.0, component))
            magnitude = abs(component)
            extent = (
                magnitude * self.half_height
                + self.radius
                * math.sqrt(max(0.0, 1.0 - component * component))
            )
            # For a rotated finite cylinder this expression and support()
            # arrive at the same mathematical extreme through different
            # floating-point paths. Expand mixed axial/radial components by
            # one representable float so the broad-phase AABB remains
            # conservative instead of occasionally excluding its own support.
            if 0.0 < magnitude < 1.0:
                extent = math.nextafter(extent, math.inf)
            return extent

        values = axis.to_tuple()
        half = Vec3(
            world_extent(values[0]),
            world_extent(values[1]),
            world_extent(values[2]),
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
    """Closed triangular convex polyhedron in local coordinates."""

    vertices: tuple[Vec3, ...]
    faces: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        try:
            vertices = tuple(self.vertices)
            faces = tuple(tuple(face) for face in self.faces)
        except TypeError as exc:
            raise PhysicsValidationError(
                "convex hull vertices/faces must be iterable"
            ) from exc

        if len(vertices) > MAX_CONVEX_HULL_VERTICES:
            raise PhysicsValidationError(
                "convex hull vertex bound exceeded"
            )
        if len(faces) > MAX_CONVEX_HULL_FACES:
            raise PhysicsValidationError(
                "convex hull face bound exceeded"
            )
        if len(vertices) < 4:
            raise PhysicsValidationError(
                "convex hull requires at least four vertices"
            )
        if len(faces) < 4:
            raise PhysicsValidationError(
                "convex hull requires at least four triangular faces"
            )
        if not all(isinstance(vertex, Vec3) for vertex in vertices):
            raise PhysicsValidationError(
                "convex hull vertices must be Vec3"
            )
        if len(set(vertices)) != len(vertices):
            raise PhysicsValidationError(
                "convex hull vertices must be unique"
            )

        minimum = vertices[0]
        maximum = vertices[0]
        for vertex in vertices[1:]:
            minimum = minimum.min(vertex)
            maximum = maximum.max(vertex)
        span = maximum - minimum
        geometry_scale = max(span.to_tuple())
        if geometry_scale <= 0.0:
            raise PhysicsValidationError(
                "convex hull vertex span must be non-zero"
            )
        area_tolerance = geometry_scale * geometry_scale * 1.0e-12
        plane_tolerance = geometry_scale**3 * 1.0e-10
        volume_tolerance = geometry_scale**3 * 1.0e-12

        normalized_faces: list[tuple[int, int, int]] = []
        directed_edges: dict[tuple[int, int], int] = {}
        undirected_edges: dict[tuple[int, int], int] = {}
        seen_faces: set[tuple[int, int, int]] = set()

        for face in faces:
            if len(face) != 3:
                raise PhysicsValidationError(
                    "convex hull faces must be triangles"
                )
            if any(
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or index >= len(vertices)
                for index in face
            ):
                raise PhysicsValidationError(
                    "convex hull face index out of range"
                )
            if len(set(face)) != 3:
                raise PhysicsValidationError(
                    "convex hull face indices must be distinct"
                )
            canonical = tuple(sorted(face))
            if canonical in seen_faces:
                raise PhysicsValidationError(
                    "convex hull contains duplicate face"
                )
            seen_faces.add(canonical)

            a, b, d = (vertices[index] for index in face)
            normal = (b - a).cross(d - a)
            if normal.length_squared() <= area_tolerance * area_tolerance:
                raise PhysicsValidationError(
                    "convex hull contains degenerate face"
                )

            signs: set[int] = set()
            for index, vertex in enumerate(vertices):
                if index in face:
                    continue
                distance = normal.dot(vertex - a)
                if distance > plane_tolerance:
                    signs.add(1)
                elif distance < -plane_tolerance:
                    signs.add(-1)
            if len(signs) > 1:
                raise PhysicsValidationError(
                    "convex hull face does not bound a convex vertex set"
                )

            normalized_faces.append(face)
            for start, end in (
                (face[0], face[1]),
                (face[1], face[2]),
                (face[2], face[0]),
            ):
                directed_edges[(start, end)] = (
                    directed_edges.get((start, end), 0) + 1
                )
                key = (min(start, end), max(start, end))
                undirected_edges[key] = undirected_edges.get(key, 0) + 1

        if any(count != 2 for count in undirected_edges.values()):
            raise PhysicsValidationError(
                "convex hull must be a closed two-manifold"
            )
        for start, end in undirected_edges:
            if (
                directed_edges.get((start, end), 0) != 1
                or directed_edges.get((end, start), 0) != 1
            ):
                raise PhysicsValidationError(
                    "convex hull face winding must be consistent"
                )

        signed_volume = 0.0
        for i, j, k in normalized_faces:
            a, b, d = vertices[i], vertices[j], vertices[k]
            signed_volume += a.dot(b.cross(d)) / 6.0
        if abs(signed_volume) <= volume_tolerance:
            raise PhysicsValidationError(
                "convex hull enclosed volume must be non-zero"
            )

        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "faces", tuple(normalized_faces))

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.CONVEX_HULL

    def aabb(self, transform: Transform) -> AABB:
        points = tuple(
            transform.transform_point(vertex)
            for vertex in self.vertices
        )
        minimum = points[0]
        maximum = points[0]
        for point in points[1:]:
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
            key=lambda row: (
                self.vertices[row].dot(local_direction),
                -row,
            ),
        )
        return transform.transform_point(self.vertices[index])

    def mass_properties(self, density: float) -> MassProperties:
        density = _positive(density, name="density")
        minimum = self.vertices[0]
        maximum = self.vertices[0]
        for vertex in self.vertices[1:]:
            minimum = minimum.min(vertex)
            maximum = maximum.max(vertex)
        geometry_scale = max((maximum - minimum).to_tuple())
        volume_tolerance = geometry_scale**3 * 1.0e-12

        volume = 0.0
        first = Vec3.zero()
        int_x2 = 0.0
        int_y2 = 0.0
        int_z2 = 0.0
        int_xy = 0.0
        int_xz = 0.0
        int_yz = 0.0

        for i, j, k in self.faces:
            a, b, c = self.vertices[i], self.vertices[j], self.vertices[k]
            tetra_volume = a.dot(b.cross(c)) / 6.0
            volume += tetra_volume
            first = first + (a + b + c) * (tetra_volume / 4.0)

            xs = (a.x, b.x, c.x)
            ys = (a.y, b.y, c.y)
            zs = (a.z, b.z, c.z)

            def square_integral(values: tuple[float, float, float]) -> float:
                x, y, z = values
                return tetra_volume * (
                    x * x + y * y + z * z
                    + x * y + x * z + y * z
                ) / 10.0

            def product_integral(
                left: tuple[float, float, float],
                right: tuple[float, float, float],
            ) -> float:
                diagonal = sum(
                    left[index] * right[index]
                    for index in range(3)
                )
                off_diagonal = sum(
                    left[i0] * right[i1]
                    for i0 in range(3)
                    for i1 in range(3)
                    if i0 != i1
                )
                return tetra_volume * (
                    2.0 * diagonal + off_diagonal
                ) / 20.0

            int_x2 += square_integral(xs)
            int_y2 += square_integral(ys)
            int_z2 += square_integral(zs)
            int_xy += product_integral(xs, ys)
            int_xz += product_integral(xs, zs)
            int_yz += product_integral(ys, zs)

        if abs(volume) <= volume_tolerance:
            raise PhysicsValidationError(
                "convex hull enclosed volume must be non-zero"
            )
        orientation_sign = 1.0 if volume > 0.0 else -1.0
        volume *= orientation_sign
        first = first * orientation_sign
        int_x2 *= orientation_sign
        int_y2 *= orientation_sign
        int_z2 *= orientation_sign
        int_xy *= orientation_sign
        int_xz *= orientation_sign
        int_yz *= orientation_sign

        center = first / volume
        mass = density * volume
        inertia_origin = Mat3(
            density * (int_y2 + int_z2),
            -density * int_xy,
            -density * int_xz,
            -density * int_xy,
            density * (int_x2 + int_z2),
            -density * int_yz,
            -density * int_xz,
            -density * int_yz,
            density * (int_x2 + int_y2),
        )

        cx, cy, cz = center.to_tuple()
        shift = Mat3(
            mass * (cy * cy + cz * cz),
            -mass * cx * cy,
            -mass * cx * cz,
            -mass * cx * cy,
            mass * (cx * cx + cz * cz),
            -mass * cy * cz,
            -mass * cx * cz,
            -mass * cy * cz,
            mass * (cx * cx + cy * cy),
        )
        inertia_com = inertia_origin + (shift * -1.0)
        return MassProperties(
            mass=mass,
            center_of_mass=center,
            inertia=inertia_com,
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
