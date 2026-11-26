"""Closest-point queries, quadrics, and attribute transfer.

Hausdorff distance in this package is one-sided: the maximum, over output
vertices, of the Euclidean distance to the closest point on the source
triangle surface. The value is produced by walking those vertices. It is not
a constant.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from skeleton.jeeves.game_frontier_production import FrontierProductionError, Vec3

from skeleton.frontier_mesh.records import (
    AREA_EPSILON,
    SEAM_POSITION_EPSILON,
    FrontierMeshError,
    SurfaceMesh,
    SurfaceVertex,
    bone_names,
    cross_length,
    renormalize,
)


@dataclass(frozen=True, slots=True)
class SurfaceHit:
    triangle_index: int
    barycentric: tuple[float, float, float]
    point: Vec3
    distance: float


def _coords(point: Vec3) -> tuple[float, float, float]:
    return (point.x, point.y, point.z)


def distance(a: Vec3, b: Vec3) -> float:
    delta = a - b
    return math.sqrt(delta.dot(delta))


def _mix(a: Vec3, b: Vec3, t: float) -> Vec3:
    return a.scaled(1.0 - t) + b.scaled(t)


def _clean_barycentric(u: float, v: float, w: float) -> tuple[float, float, float]:
    coords = [0.0 if -1e-10 < value < 0.0 else value for value in (u, v, w)]
    total = math.fsum(coords)
    if not math.isfinite(total) or total <= AREA_EPSILON:
        raise FrontierMeshError("weight table does not sum to 1")
    return (coords[0] / total, coords[1] / total, coords[2] / total)


def closest_on_triangle(point: Vec3, a: Vec3, b: Vec3, c: Vec3) -> tuple[Vec3, tuple[float, float, float]]:
    """Ericson closest point. Barycentric coordinates sum to 1."""
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
        denom = d1 - d3
        v = d1 / denom if denom != 0.0 else 0.0
        return _mix(a, b, v), _clean_barycentric(1.0 - v, v, 0.0)
    cp = point - c
    d5 = ab.dot(cp)
    d6 = ac.dot(cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        denom = d2 - d6
        w = d2 / denom if denom != 0.0 else 0.0
        return _mix(a, c, w), _clean_barycentric(1.0 - w, 0.0, w)
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        denom = (d4 - d3) + (d5 - d6)
        w = (d4 - d3) / denom if denom != 0.0 else 0.0
        return _mix(b, c, w), _clean_barycentric(0.0, 1.0 - w, w)
    denom = va + vb + vc
    if denom == 0.0 or not math.isfinite(denom):
        return a, (1.0, 0.0, 0.0)
    v = vb / denom
    w = vc / denom
    hit = a + ab.scaled(v) + ac.scaled(w)
    return hit, _clean_barycentric(1.0 - v - w, v, w)


def closest_point(point: Vec3, mesh: SurfaceMesh) -> SurfaceHit:
    """Closest point on ``mesh``. Equal distances keep the lowest triangle index."""
    best: SurfaceHit | None = None
    for index, triangle in enumerate(mesh.triangles):
        a, b, c = (mesh.vertices[vertex].position for vertex in triangle.indices)
        if cross_length(a, b, c) < AREA_EPSILON:
            continue
        hit, barycentric = closest_on_triangle(point, a, b, c)
        gap = distance(point, hit)
        if best is None or gap < best.distance - 1e-15:
            best = SurfaceHit(index, barycentric, hit, gap)
    if best is None:
        raise FrontierMeshError("zero-area triangle")
    return best


def directed_hausdorff(points: tuple[Vec3, ...] | list[Vec3], mesh: SurfaceMesh) -> float:
    """Max distance from each point to ``mesh``, computed by closest-point tests."""
    if not points:
        raise FrontierMeshError("hausdorff requires vertices")
    worst = 0.0
    for point in points:
        gap = closest_point(point, mesh).distance
        if gap > worst:
            worst = gap
    return worst


def seam_groups(mesh: SurfaceMesh) -> tuple[tuple[int, ...], ...]:
    """Groups of vertices within ``SEAM_POSITION_EPSILON`` that span 2+ materials."""
    count = len(mesh.vertices)
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a == b:
            return
        if a < b:
            parent[b] = a
        else:
            parent[a] = b

    materials: list[set[str]] = [set() for _ in range(count)]
    for triangle in mesh.triangles:
        for index in triangle.indices:
            materials[index].add(triangle.material)
    for i in range(count):
        for j in range(i + 1, count):
            if distance(mesh.vertices[i].position, mesh.vertices[j].position) <= SEAM_POSITION_EPSILON:
                union(i, j)
    buckets: dict[int, list[int]] = {}
    for index in range(count):
        buckets.setdefault(find(index), []).append(index)
    groups: list[tuple[int, ...]] = []
    for members in buckets.values():
        covered: set[str] = set()
        for index in members:
            covered |= materials[index]
        if len(covered) >= 2:
            groups.append(tuple(sorted(members)))
    groups.sort()
    return tuple(groups)


def seam_position_delta(mesh: SurfaceMesh) -> float:
    """Largest distance between copies of one seam. Computed, not assumed."""
    worst = 0.0
    for group in seam_groups(mesh):
        for left in range(len(group)):
            for right in range(left + 1, len(group)):
                gap = distance(
                    mesh.vertices[group[left]].position,
                    mesh.vertices[group[right]].position,
                )
                if gap > worst:
                    worst = gap
    return worst


def blend_attributes(
    barycentric: tuple[float, float, float],
    corners: tuple[SurfaceVertex, SurfaceVertex, SurfaceVertex],
) -> tuple[Vec3, tuple[float, float], dict[str, float]]:
    """Barycentric normal, UV, and bone-name weights. The normal is not yet unit."""
    u, v, w = barycentric
    normal = (
        corners[0].normal.scaled(u)
        + corners[1].normal.scaled(v)
        + corners[2].normal.scaled(w)
    )
    if math.sqrt(normal.dot(normal)) < AREA_EPSILON:
        geometric = (corners[1].position - corners[0].position).cross(
            corners[2].position - corners[0].position
        )
        if math.sqrt(geometric.dot(geometric)) < AREA_EPSILON:
            raise FrontierMeshError("zero-length normal")
        normal = geometric
    uv = (
        corners[0].uv[0] * u + corners[1].uv[0] * v + corners[2].uv[0] * w,
        corners[0].uv[1] * u + corners[1].uv[1] * v + corners[2].uv[1] * w,
    )
    weights: dict[str, float] = {}
    for bary, corner in zip((u, v, w), corners, strict=True):
        if bary == 0.0:
            continue
        for entry in corner.weights:
            weights[entry.bone_name] = weights.get(entry.bone_name, 0.0) + bary * entry.weight
    return normal, uv, weights


def sample_surface(point: Vec3, mesh: SurfaceMesh) -> tuple[Vec3, tuple[float, float], dict[str, float]]:
    hit = closest_point(point, mesh)
    corners = tuple(mesh.vertices[index] for index in mesh.triangles[hit.triangle_index].indices)
    return blend_attributes(hit.barycentric, corners)  # type: ignore[arg-type]


def transferred_weights(
    point: Vec3,
    source: SurfaceMesh,
    *,
    allowed_bones: frozenset[str] | None,
) -> tuple:
    """Skin weights at the closest source point, then renormalized to 1.

    Bone identity is the bone name. ``allowed_bones`` drops every other name
    before the renormalize, which is how a target skeleton subset is applied.
    """
    _normal, _uv, weights = sample_surface(point, source)
    if allowed_bones is not None:
        weights = {name: value for name, value in weights.items() if name in allowed_bones}
    return renormalize(weights)


def source_bone_names(mesh: SurfaceMesh) -> frozenset[str]:
    names = bone_names(mesh)
    if not names:
        raise FrontierMeshError("weight table does not sum to 1")
    return names


def assert_bone_subset(target: frozenset[str] | set[str], source: SurfaceMesh) -> None:
    if not set(target) <= set(source_bone_names(source)):
        raise FrontierMeshError("target bone names are not a subset of the source")


def scale_position(point: Vec3, scale: float) -> Vec3:
    try:
        return point.scaled(scale)
    except FrontierProductionError as exc:
        raise FrontierMeshError("non-finite coordinate") from exc


def quadric_from_triangle(a: Vec3, b: Vec3, c: Vec3) -> tuple[float, ...] | None:
    """Garland-Heckbert plane quadric, stored as the 10 unique 4x4 entries."""
    length = cross_length(a, b, c)
    if length < AREA_EPSILON or not math.isfinite(length):
        return None
    normal = (b - a).cross(c - a).scaled(1.0 / length)
    offset = -(normal.x * a.x + normal.y * a.y + normal.z * a.z)
    plane = (normal.x, normal.y, normal.z, offset)
    values: list[float] = []
    for row in range(4):
        for col in range(row, 4):
            values.append(plane[row] * plane[col])
    return tuple(values)


def add_quadric(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(a + b for a, b in zip(left, right, strict=True))


def quadric_error(quadric: tuple[float, ...], point: Vec3) -> float:
    q00, q01, q02, q03, q11, q12, q13, q22, q23, q33 = quadric
    x, y, z = point.x, point.y, point.z
    return (
        q00 * x * x
        + 2.0 * q01 * x * y
        + 2.0 * q02 * x * z
        + 2.0 * q03 * x
        + q11 * y * y
        + 2.0 * q12 * y * z
        + 2.0 * q13 * y
        + q22 * z * z
        + 2.0 * q23 * z
        + q33
    )


def solve_quadric(quadric: tuple[float, ...]) -> Vec3 | None:
    """Optimal vertex for a quadric. ``None`` when the 3x3 block is singular."""
    q00, q01, q02, q03, q11, q12, q13, q22, q23, _q33 = quadric
    matrix = [
        [q00, q01, q02, -q03],
        [q01, q11, q12, -q13],
        [q02, q12, q22, -q23],
    ]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(matrix[row][col]))
        if abs(matrix[pivot][col]) < 1e-12:
            return None
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        divisor = matrix[col][col]
        for column in range(col, 4):
            matrix[col][column] /= divisor
        for row in range(3):
            if row == col:
                continue
            factor = matrix[row][col]
            for column in range(col, 4):
                matrix[row][column] -= factor * matrix[col][column]
    x, y, z = matrix[0][3], matrix[1][3], matrix[2][3]
    if not all(math.isfinite(value) and abs(value) <= 1e5 for value in (x, y, z)):
        return None
    try:
        return Vec3(x, y, z)
    except FrontierProductionError:
        return None
