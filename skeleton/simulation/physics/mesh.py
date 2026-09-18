"""Deterministic static triangle-mesh geometry with a stable local-space BVH."""
from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass, field

from .errors import PhysicsValidationError
from .math3d import AABB, Transform, Vec3
from .shapes import MassProperties, ShapeKind

MAX_MESH_VERTICES = 1_000_000
MAX_MESH_TRIANGLES = 2_000_000
_BVH_LEAF_TRIANGLES = 4
_GEOMETRY_EPSILON_SQ = 1.0e-24


@dataclass(frozen=True, slots=True)
class MeshBVHNode:
    bounds: AABB
    left: int | None = None
    right: int | None = None
    triangles: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        leaf = bool(self.triangles)
        internal = self.left is not None or self.right is not None
        if leaf == internal:
            raise PhysicsValidationError(
                "mesh BVH node must be exactly leaf or internal"
            )
        if internal and (self.left is None or self.right is None):
            raise PhysicsValidationError(
                "mesh BVH internal node requires two children"
            )
        if leaf:
            if tuple(sorted(self.triangles)) != self.triangles:
                raise PhysicsValidationError(
                    "mesh BVH leaf triangles must be sorted"
                )
            if len(set(self.triangles)) != len(self.triangles):
                raise PhysicsValidationError(
                    "mesh BVH leaf triangles must be unique"
                )


@dataclass(frozen=True, slots=True)
class MeshRayHit:
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
                "mesh ray triangle index must be non-negative integer"
            )
        if not math.isfinite(self.distance) or self.distance < 0.0:
            raise PhysicsValidationError(
                "mesh ray distance must be finite and non-negative"
            )
        object.__setattr__(self, "normal", self.normal.normalized())
        if len(self.barycentric) != 3:
            raise PhysicsValidationError(
                "mesh ray barycentric must contain three weights"
            )
        if any(not math.isfinite(value) for value in self.barycentric):
            raise PhysicsValidationError(
                "mesh ray barycentric weights must be finite"
            )


def _bounds_for_points(points: tuple[Vec3, ...]) -> AABB:
    if not points:
        raise PhysicsValidationError("mesh bounds require points")
    minimum = points[0]
    maximum = points[0]
    for point in points[1:]:
        minimum = minimum.min(point)
        maximum = maximum.max(point)
    return AABB(minimum, maximum)


def _ray_aabb(
    origin: Vec3,
    direction: Vec3,
    bounds: AABB,
    max_distance: float,
) -> tuple[float, float] | None:
    near = 0.0
    far = max_distance
    for axis in range(3):
        o = origin.to_tuple()[axis]
        d = direction.to_tuple()[axis]
        lower = bounds.minimum.to_tuple()[axis]
        upper = bounds.maximum.to_tuple()[axis]
        if abs(d) <= 1.0e-12:
            if o < lower or o > upper:
                return None
            continue
        inverse = 1.0 / d
        first = (lower - o) * inverse
        second = (upper - o) * inverse
        if first > second:
            first, second = second, first
        near = max(near, first)
        far = min(far, second)
        if near > far:
            return None
    return near, far


@dataclass(frozen=True, slots=True)
class SegmentTriangleClosest:
    segment_point: Vec3
    triangle_point: Vec3
    segment_parameter: float
    barycentric: tuple[float, float, float]

    @property
    def distance_squared(self) -> float:
        return (
            self.segment_point - self.triangle_point
        ).length_squared()


def closest_points_on_segments(
    first_start: Vec3,
    first_end: Vec3,
    second_start: Vec3,
    second_end: Vec3,
) -> tuple[Vec3, Vec3, float, float]:
    """Closest points on two finite segments with deterministic clamping."""

    first_delta = first_end - first_start
    second_delta = second_end - second_start
    relative = first_start - second_start
    first_length_sq = first_delta.length_squared()
    second_length_sq = second_delta.length_squared()

    if (
        first_length_sq <= _GEOMETRY_EPSILON_SQ
        and second_length_sq <= _GEOMETRY_EPSILON_SQ
    ):
        return first_start, second_start, 0.0, 0.0

    if first_length_sq <= _GEOMETRY_EPSILON_SQ:
        first_t = 0.0
        second_t = min(
            1.0,
            max(
                0.0,
                second_delta.dot(first_start - second_start)
                / second_length_sq,
            ),
        )
    else:
        first_dot = first_delta.dot(relative)
        if second_length_sq <= _GEOMETRY_EPSILON_SQ:
            second_t = 0.0
            first_t = min(
                1.0,
                max(0.0, -first_dot / first_length_sq),
            )
        else:
            cross_dot = first_delta.dot(second_delta)
            second_dot = second_delta.dot(relative)
            denominator = (
                first_length_sq * second_length_sq
                - cross_dot * cross_dot
            )
            if abs(denominator) > _GEOMETRY_EPSILON_SQ:
                first_t = min(
                    1.0,
                    max(
                        0.0,
                        (
                            cross_dot * second_dot
                            - first_dot * second_length_sq
                        )
                        / denominator,
                    ),
                )
            else:
                first_t = 0.0

            second_t = (
                cross_dot * first_t + second_dot
            ) / second_length_sq
            if second_t < 0.0:
                second_t = 0.0
                first_t = min(
                    1.0,
                    max(0.0, -first_dot / first_length_sq),
                )
            elif second_t > 1.0:
                second_t = 1.0
                first_t = min(
                    1.0,
                    max(
                        0.0,
                        (cross_dot - first_dot) / first_length_sq,
                    ),
                )

    first_point = first_start + first_delta * first_t
    second_point = second_start + second_delta * second_t
    return first_point, second_point, first_t, second_t


def _segment_triangle_intersection(
    start: Vec3,
    end: Vec3,
    a: Vec3,
    b: Vec3,
    c: Vec3,
) -> SegmentTriangleClosest | None:
    direction = end - start
    edge1 = b - a
    edge2 = c - a
    p = direction.cross(edge2)
    determinant = edge1.dot(p)
    if abs(determinant) <= 1.0e-12:
        return None

    inverse = 1.0 / determinant
    tvec = start - a
    u = tvec.dot(p) * inverse
    if u < -1.0e-10 or u > 1.0 + 1.0e-10:
        return None

    q = tvec.cross(edge1)
    v = direction.dot(q) * inverse
    if v < -1.0e-10 or u + v > 1.0 + 1.0e-10:
        return None

    segment_t = edge2.dot(q) * inverse
    if segment_t < -1.0e-10 or segment_t > 1.0 + 1.0e-10:
        return None
    segment_t = min(1.0, max(0.0, segment_t))
    point = start + direction * segment_t
    return SegmentTriangleClosest(
        segment_point=point,
        triangle_point=point,
        segment_parameter=segment_t,
        barycentric=(1.0 - u - v, u, v),
    )


def closest_points_segment_triangle(
    start: Vec3,
    end: Vec3,
    a: Vec3,
    b: Vec3,
    c: Vec3,
) -> SegmentTriangleClosest:
    """Exact closest pair between one finite segment and one triangle."""

    intersection = _segment_triangle_intersection(
        start,
        end,
        a,
        b,
        c,
    )
    if intersection is not None:
        return intersection

    candidates: list[tuple[float, int, SegmentTriangleClosest]] = []

    start_triangle, start_weights = closest_point_on_triangle(
        start,
        a,
        b,
        c,
    )
    start_result = SegmentTriangleClosest(
        segment_point=start,
        triangle_point=start_triangle,
        segment_parameter=0.0,
        barycentric=start_weights,
    )
    candidates.append((start_result.distance_squared, 0, start_result))

    end_triangle, end_weights = closest_point_on_triangle(
        end,
        a,
        b,
        c,
    )
    end_result = SegmentTriangleClosest(
        segment_point=end,
        triangle_point=end_triangle,
        segment_parameter=1.0,
        barycentric=end_weights,
    )
    candidates.append((end_result.distance_squared, 1, end_result))

    edges = (
        (a, b, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        (b, c, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        (c, a, (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    )
    for edge_index, (
        edge_start,
        edge_end,
        start_weights,
        end_weights,
    ) in enumerate(edges):
        segment_point, edge_point, segment_t, edge_t = (
            closest_points_on_segments(
                start,
                end,
                edge_start,
                edge_end,
            )
        )
        weights = tuple(
            start_weights[index] * (1.0 - edge_t)
            + end_weights[index] * edge_t
            for index in range(3)
        )
        result = SegmentTriangleClosest(
            segment_point=segment_point,
            triangle_point=edge_point,
            segment_parameter=segment_t,
            barycentric=weights,  # type: ignore[arg-type]
        )
        candidates.append(
            (
                result.distance_squared,
                2 + edge_index,
                result,
            )
        )

    return min(
        candidates,
        key=lambda row: (
            row[0],
            row[1],
            row[2].segment_parameter,
            row[2].barycentric,
        ),
    )[2]


def closest_point_on_triangle(
    point: Vec3,
    a: Vec3,
    b: Vec3,
    c: Vec3,
) -> tuple[Vec3, tuple[float, float, float]]:
    """Closest point and barycentric weights using triangle Voronoi regions."""

    ab = b - a
    ac = c - a
    ap = point - a
    d1 = ab.dot(ap)
    d2 = ac.dot(ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a, (1.0, 0.0, 0.0)

    bp = point - b
    d3 = ab.dot(bp)
    d4 = ac.dot(bp)
    if d3 >= 0.0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        denominator = d1 - d3
        if abs(denominator) <= 1.0e-20:
            return a, (1.0, 0.0, 0.0)
        v = d1 / denominator
        return a + ab * v, (1.0 - v, v, 0.0)

    cp = point - c
    d5 = ab.dot(cp)
    d6 = ac.dot(cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        denominator = d2 - d6
        if abs(denominator) <= 1.0e-20:
            return a, (1.0, 0.0, 0.0)
        w = d2 / denominator
        return a + ac * w, (1.0 - w, 0.0, w)

    va = d3 * d6 - d5 * d4
    if (
        va <= 0.0
        and (d4 - d3) >= 0.0
        and (d5 - d6) >= 0.0
    ):
        denominator = (d4 - d3) + (d5 - d6)
        if abs(denominator) <= 1.0e-20:
            return b, (0.0, 1.0, 0.0)
        w = (d4 - d3) / denominator
        return b + (c - b) * w, (0.0, 1.0 - w, w)

    denominator = va + vb + vc
    if abs(denominator) <= 1.0e-20:
        candidates = (
            closest_point_on_segment(point, a, b, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            closest_point_on_segment(point, a, c, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            closest_point_on_segment(point, b, c, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        )
        return min(
            candidates,
            key=lambda row: (
                (row[0] - point).length_squared(),
                row[1],
            ),
        )

    inverse = 1.0 / denominator
    v = vb * inverse
    w = vc * inverse
    u = 1.0 - v - w
    return a * u + b * v + c * w, (u, v, w)


def closest_point_on_segment(
    point: Vec3,
    start: Vec3,
    end: Vec3,
    start_weights: tuple[float, float, float],
    end_weights: tuple[float, float, float],
) -> tuple[Vec3, tuple[float, float, float]]:
    edge = end - start
    denominator = edge.length_squared()
    if denominator <= _GEOMETRY_EPSILON_SQ:
        return start, start_weights
    t = (point - start).dot(edge) / denominator
    t = min(1.0, max(0.0, t))
    weights = tuple(
        start_weights[index] * (1.0 - t) + end_weights[index] * t
        for index in range(3)
    )
    return start + edge * t, weights  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class TriangleMeshShape:
    """Finite concave triangle mesh with deterministic local-space BVH."""

    vertices: tuple[Vec3, ...]
    triangles: tuple[tuple[int, int, int], ...]
    _triangle_bounds: tuple[AABB, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _centroids: tuple[Vec3, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _nodes: tuple[MeshBVHNode, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _root: int = field(init=False, repr=False, compare=False)
    _local_bounds: AABB = field(init=False, repr=False, compare=False)
    _geometry_fingerprint: str = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        try:
            vertices = tuple(self.vertices)
            triangles = tuple(tuple(row) for row in self.triangles)
        except TypeError as exc:
            raise PhysicsValidationError(
                "mesh vertices/triangles must be iterable"
            ) from exc

        if not 3 <= len(vertices) <= MAX_MESH_VERTICES:
            raise PhysicsValidationError(
                "mesh vertex count outside supported range"
            )
        if not 1 <= len(triangles) <= MAX_MESH_TRIANGLES:
            raise PhysicsValidationError(
                "mesh triangle count outside supported range"
            )
        if not all(isinstance(vertex, Vec3) for vertex in vertices):
            raise PhysicsValidationError("mesh vertices must be Vec3")

        seen: set[tuple[int, int, int]] = set()
        triangle_bounds: list[AABB] = []
        centroids: list[Vec3] = []
        for triangle in triangles:
            if len(triangle) != 3:
                raise PhysicsValidationError(
                    "mesh triangles must contain three indices"
                )
            if any(
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or index >= len(vertices)
                for index in triangle
            ):
                raise PhysicsValidationError(
                    "mesh triangle index out of range"
                )
            if len(set(triangle)) != 3:
                raise PhysicsValidationError(
                    "mesh triangle indices must be distinct"
                )
            canonical = tuple(sorted(triangle))
            if canonical in seen:
                raise PhysicsValidationError(
                    "mesh contains duplicate triangle"
                )
            seen.add(canonical)
            a, b, c = (vertices[index] for index in triangle)
            normal = (b - a).cross(c - a)
            if normal.length_squared() <= _GEOMETRY_EPSILON_SQ:
                raise PhysicsValidationError(
                    "mesh contains degenerate triangle"
                )
            triangle_bounds.append(_bounds_for_points((a, b, c)))
            centroids.append((a + b + c) / 3.0)

        local_bounds = _bounds_for_points(vertices)
        nodes: list[MeshBVHNode] = []

        def build(indices: tuple[int, ...]) -> int:
            bounds = triangle_bounds[indices[0]]
            for triangle_index in indices[1:]:
                bounds = bounds.combine(triangle_bounds[triangle_index])

            if len(indices) <= _BVH_LEAF_TRIANGLES:
                node_index = len(nodes)
                nodes.append(
                    MeshBVHNode(
                        bounds=bounds,
                        triangles=tuple(sorted(indices)),
                    )
                )
                return node_index

            centroid_points = tuple(centroids[index] for index in indices)
            centroid_bounds = _bounds_for_points(centroid_points)
            extent = centroid_bounds.maximum - centroid_bounds.minimum
            extents = extent.to_tuple()
            axis = max(
                range(3),
                key=lambda candidate: (
                    extents[candidate],
                    -candidate,
                ),
            )
            ordered = tuple(
                sorted(
                    indices,
                    key=lambda triangle_index: (
                        centroids[triangle_index].to_tuple()[axis],
                        triangle_index,
                    ),
                )
            )
            middle = len(ordered) // 2
            left = build(ordered[:middle])
            right = build(ordered[middle:])
            node_index = len(nodes)
            nodes.append(
                MeshBVHNode(
                    bounds=bounds,
                    left=left,
                    right=right,
                )
            )
            return node_index

        root = build(tuple(range(len(triangles))))

        digest = hashlib.sha256()
        digest.update(struct.pack(">QQ", len(vertices), len(triangles)))
        for vertex in vertices:
            digest.update(struct.pack(">ddd", *vertex.to_tuple()))
        for triangle in triangles:
            digest.update(struct.pack(">QQQ", *triangle))

        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "triangles", triangles)
        object.__setattr__(self, "_triangle_bounds", tuple(triangle_bounds))
        object.__setattr__(self, "_centroids", tuple(centroids))
        object.__setattr__(self, "_nodes", tuple(nodes))
        object.__setattr__(self, "_root", root)
        object.__setattr__(self, "_local_bounds", local_bounds)
        object.__setattr__(self, "_geometry_fingerprint", digest.hexdigest())

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.TRIANGLE_MESH

    @property
    def geometry_fingerprint(self) -> str:
        return self._geometry_fingerprint  # type: ignore[attr-defined]

    @property
    def bvh_node_count(self) -> int:
        return len(self._nodes)  # type: ignore[attr-defined]

    @property
    def local_bounds(self) -> AABB:
        return self._local_bounds  # type: ignore[attr-defined]

    def triangle_vertices(self, index: int) -> tuple[Vec3, Vec3, Vec3]:
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(self.triangles)
        ):
            raise PhysicsValidationError("mesh triangle index out of range")
        triangle = self.triangles[index]
        return tuple(self.vertices[i] for i in triangle)  # type: ignore[return-value]

    def triangle_normal(self, index: int) -> Vec3:
        a, b, c = self.triangle_vertices(index)
        return (b - a).cross(c - a).normalized()

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
        if local_direction.length_squared() <= _GEOMETRY_EPSILON_SQ:
            raise PhysicsValidationError(
                "mesh support direction must be non-zero"
            )
        index = max(
            range(len(self.vertices)),
            key=lambda candidate: (
                self.vertices[candidate].dot(local_direction),
                -candidate,
            ),
        )
        return transform.transform_point(self.vertices[index])

    def mass_properties(self, density: float) -> MassProperties:
        del density
        raise PhysicsValidationError(
            "triangle meshes are concave static geometry and have no dynamic mass properties"
        )

    def candidate_triangles(self, bounds: AABB) -> tuple[int, ...]:
        if not isinstance(bounds, AABB):
            raise PhysicsValidationError(
                "mesh candidate query requires AABB"
            )
        nodes: tuple[MeshBVHNode, ...] = self._nodes  # type: ignore[attr-defined]
        stack = [self._root]  # type: ignore[attr-defined]
        result: set[int] = set()
        while stack:
            node_index = stack.pop()
            node = nodes[node_index]
            if not node.bounds.overlaps(bounds):
                continue
            if node.triangles:
                result.update(node.triangles)
            else:
                assert node.left is not None and node.right is not None
                stack.append(node.right)
                stack.append(node.left)
        return tuple(sorted(result))

    def raycast_local(
        self,
        origin: Vec3,
        direction: Vec3,
        max_distance: float,
    ) -> MeshRayHit | None:
        if not isinstance(origin, Vec3) or not isinstance(direction, Vec3):
            raise PhysicsValidationError(
                "mesh ray origin/direction must be Vec3"
            )
        direction = direction.normalized()
        if (
            isinstance(max_distance, bool)
            or not isinstance(max_distance, (int, float))
            or not math.isfinite(float(max_distance))
            or float(max_distance) < 0.0
        ):
            raise PhysicsValidationError(
                "mesh ray max_distance must be finite and non-negative"
            )
        max_distance = float(max_distance)

        nodes: tuple[MeshBVHNode, ...] = self._nodes  # type: ignore[attr-defined]
        stack = [self._root]  # type: ignore[attr-defined]
        candidates: list[MeshRayHit] = []

        while stack:
            node_index = stack.pop()
            node = nodes[node_index]
            interval = _ray_aabb(
                origin,
                direction,
                node.bounds,
                max_distance,
            )
            if interval is None:
                continue
            if node.triangles:
                for triangle_index in node.triangles:
                    hit = self._ray_triangle(
                        triangle_index,
                        origin,
                        direction,
                        max_distance,
                    )
                    if hit is not None:
                        candidates.append(hit)
            else:
                assert node.left is not None and node.right is not None
                stack.append(node.right)
                stack.append(node.left)

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
    ) -> MeshRayHit | None:
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
        w = 1.0 - u - v
        return MeshRayHit(
            triangle_index=triangle_index,
            distance=distance,
            point=origin + direction * distance,
            normal=normal,
            barycentric=(w, u, v),
        )
