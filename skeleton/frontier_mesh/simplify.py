"""Quadric edge-collapse LOD and source-to-target retarget.

Collapse uses Garland-Heckbert plane quadrics. The placement for an edge is
the lowest-error finite candidate among the quadric optimum, the midpoint,
and the two endpoints, in that order on a tie. Edges are tried from lowest
error, then lowest endpoint indices, so the same source and face budget
always produce the same vertex digest.

Skin weights on every output vertex are resampled from the closest point on
the original source surface. Barycentric coordinates mix the source corner
weights by bone name, then the table is renormalized to 1. A target bone set
that is not a subset of the source is rejected before that transfer.

Seam copies (see ``SEAM_POSITION_EPSILON``) are locked to one position for
the whole collapse, so both materials keep matching coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from skeleton.jeeves.game_frontier_production import FrontierProductionError, Vec3

from skeleton.frontier_mesh.records import (
    AREA_EPSILON,
    SEAM_POSITION_EPSILON,
    WEIGHT_SUM_EPSILON,
    FrontierMeshError,
    SurfaceMesh,
    SurfaceTriangle,
    SurfaceVertex,
    _bounded,
    _finite,
    bone_names,
    cross_length,
    renormalize,
    vertex_digest,
)
from skeleton.frontier_mesh.surface import (
    add_quadric,
    assert_bone_subset,
    directed_hausdorff,
    quadric_error,
    quadric_from_triangle,
    sample_surface,
    scale_position,
    seam_groups,
    seam_position_delta,
    solve_quadric,
)


_ZERO_QUADRIC = (0.0,) * 10


@dataclass(frozen=True, slots=True)
class MeshLod:
    """LOD or retarget result.

    ``hausdorff_max`` is the max distance from each output vertex to the
    source surface in the same position space as ``mesh``. The number is
    measured with closest-point queries inside :func:`directed_hausdorff`.
    ``seam_position_delta`` is the max distance between surviving copies of
    one seam and is required to stay within ``SEAM_POSITION_EPSILON``.
    """

    mesh: SurfaceMesh
    face_budget: int
    hausdorff_max: float
    seam_position_delta: float
    vertex_digest: str


def _find(parent: list[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _union(parent: list[int], left: int, right: int) -> None:
    a, b = _find(parent, left), _find(parent, right)
    if a == b:
        return
    if a < b:
        parent[b] = a
    else:
        parent[a] = b


def _lock_groups(mesh: SurfaceMesh) -> list[int]:
    """Lock seam copies that ``seam_groups`` reports within ``SEAM_POSITION_EPSILON``."""
    lock = list(range(len(mesh.vertices)))
    for group in seam_groups(mesh):
        if len(group) < 2:
            continue
        for other in group[1:]:
            _union(lock, group[0], other)
    return lock


def _face_quadrics(
    positions: Sequence[Vec3],
    triangles: Sequence[tuple[int, int, int, str]],
) -> dict[int, tuple[float, ...]]:
    accum: dict[int, tuple[float, ...]] = {}
    for a, b, c, _material in triangles:
        quadric = quadric_from_triangle(positions[a], positions[b], positions[c])
        if quadric is None:
            continue
        for index in (a, b, c):
            current = accum.get(index, _ZERO_QUADRIC)
            accum[index] = add_quadric(current, quadric)
    return accum


def _try_collapse(
    i: int,
    j: int,
    new_pos: Vec3,
    positions: Sequence[Vec3],
    triangles: Sequence[tuple[int, int, int, str]],
    rep: Sequence[int],
    lock: Sequence[int],
) -> tuple[list[Vec3], list[tuple[int, int, int, str]], list[int], list[int]] | None:
    positions = list(positions)
    triangles = list(triangles)
    rep = list(rep)
    lock = list(lock)
    left, right = _find(rep, i), _find(rep, j)
    if left == right:
        return None
    survivor = min(left, right)
    removed = max(left, right)
    _union(lock, survivor, removed)
    rep[removed] = survivor
    root = _find(lock, survivor)
    count = len(positions)
    for vertex in range(count):
        if _find(lock, vertex) == root:
            positions[_find(rep, vertex)] = new_pos
    rebuilt: list[tuple[int, int, int, str]] = []
    seen: set[tuple[int, int, int, str]] = set()
    for a, b, c, material in triangles:
        aa, bb, cc = _find(rep, a), _find(rep, b), _find(rep, c)
        if len({aa, bb, cc}) < 3:
            continue
        face = (aa, bb, cc, material)
        if face in seen:
            continue
        seen.add(face)
        if cross_length(positions[aa], positions[bb], positions[cc]) < AREA_EPSILON:
            return None
        rebuilt.append(face)
    if not rebuilt or len(rebuilt) >= len(triangles):
        return None
    return positions, rebuilt, rep, lock


def _placement_candidates(
    i: int,
    j: int,
    positions: Sequence[Vec3],
    quadric: tuple[float, ...],
) -> tuple[Vec3 | None, ...]:
    return (
        solve_quadric(quadric),
        Vec3(
            (positions[i].x + positions[j].x) * 0.5,
            (positions[i].y + positions[j].y) * 0.5,
            (positions[i].z + positions[j].z) * 0.5,
        ),
        positions[i],
        positions[j],
    )


def _collapse_to_budget(
    mesh: SurfaceMesh,
    face_budget: int,
) -> tuple[list[Vec3], list[tuple[int, int, int, str]]]:
    positions: list[Vec3] = [vertex.position for vertex in mesh.vertices]
    triangles = [
        (triangle.indices[0], triangle.indices[1], triangle.indices[2], triangle.material)
        for triangle in mesh.triangles
    ]
    rep = list(range(len(positions)))
    lock = _lock_groups(mesh)
    if len(triangles) <= face_budget:
        return positions, triangles
    guard = len(triangles)
    while len(triangles) > face_budget:
        guard -= 1
        if guard < 0:
            raise FrontierMeshError("face budget unreachable")
        quadrics = _face_quadrics(positions, triangles)
        ranked: list[tuple[float, int, int, Vec3, tuple]] = []
        seen_edges: set[tuple[int, int]] = set()
        for a, b, c, _material in triangles:
            for u, v in ((a, b), (b, c), (c, a)):
                if u > v:
                    u, v = v, u
                if u == v or (u, v) in seen_edges:
                    continue
                seen_edges.add((u, v))
                quadric = add_quadric(quadrics.get(u, _ZERO_QUADRIC), quadrics.get(v, _ZERO_QUADRIC))
                best: tuple[float, int, Vec3, tuple] | None = None
                for order, candidate in enumerate(_placement_candidates(u, v, positions, quadric)):
                    if candidate is None:
                        continue
                    if not all(math.isfinite(component) for component in (candidate.x, candidate.y, candidate.z)):
                        continue
                    state = _try_collapse(u, v, candidate, positions, triangles, rep, lock)
                    if state is None:
                        continue
                    error = quadric_error(quadric, candidate)
                    if not math.isfinite(error):
                        continue
                    if best is None or error < best[0] - 1e-15:
                        best = (error, order, candidate, state)
                if best is not None:
                    ranked.append((best[0], u, v, best[2], best[3]))
        if not ranked:
            raise FrontierMeshError("face budget unreachable")
        # Quantize only the sort key so coplanar edges, whose quadric errors
        # differ by solver noise, collapse in endpoint-index order.
        ranked.sort(key=lambda item: (round(item[0], 12), item[1], item[2]))
        positions, triangles, rep, lock = ranked[0][4]
    return positions, triangles


def _positive_scale(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FrontierMeshError("non-finite coordinate")
    number = _finite(value)
    if number == 0.0:
        raise FrontierMeshError("zero-area triangle")
    _bounded(number)
    return number


def _uv_scale(value: object) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise FrontierMeshError("texture coordinate must be a pair")
    return (_finite(value[0]), _finite(value[1]))


def _bone_argument(target_bones: Sequence[str] | None) -> frozenset[str] | None:
    if target_bones is None:
        return None
    if isinstance(target_bones, str):
        raise FrontierMeshError("target bone names are not a subset of the source")
    names: set[str] = set()
    for name in target_bones:
        if not isinstance(name, str) or not name:
            raise FrontierMeshError("invalid bone name")
        names.add(name)
    return frozenset(names)


def _reference_mesh(source: SurfaceMesh, position_scale: float) -> SurfaceMesh:
    flip = position_scale < 0.0
    vertices = tuple(
        SurfaceVertex(
            scale_position(vertex.position, position_scale),
            vertex.normal.scaled(-1.0) if flip else vertex.normal,
            vertex.uv,
            vertex.weights,
        )
        for vertex in source.vertices
    )
    return SurfaceMesh(vertices, source.triangles)


def _assemble(
    source: SurfaceMesh,
    geometry: SurfaceMesh,
    positions: Sequence[Vec3],
    triangles: Sequence[tuple[int, int, int, str]],
    *,
    uv_scale: tuple[float, float],
    position_scale: float,
    allowed_bones: frozenset[str] | None,
) -> SurfaceMesh:
    used = sorted({index for face in triangles for index in face[:3]})
    remap = {old: new for new, old in enumerate(used)}
    flip = position_scale < 0.0
    built: list[SurfaceVertex] = []
    for old in used:
        local = positions[old]
        if geometry is source:
            normal, uv, weights = sample_surface(local, source)
        else:
            normal, uv, _target_weights = sample_surface(local, geometry)
            _source_normal, _source_uv, weights = sample_surface(local, source)
        if allowed_bones is not None:
            weights = {name: value for name, value in weights.items() if name in allowed_bones}
        table = renormalize(weights)
        if flip:
            try:
                normal = normal.scaled(-1.0)
            except FrontierProductionError as exc:
                raise FrontierMeshError("non-finite coordinate") from exc
        length = math.sqrt(normal.dot(normal))
        if length < AREA_EPSILON or not math.isfinite(length):
            raise FrontierMeshError("zero-length normal")
        try:
            normal = normal.scaled(1.0 / length)
        except FrontierProductionError as exc:
            raise FrontierMeshError("non-finite coordinate") from exc
        if abs(math.sqrt(normal.dot(normal)) - 1.0) > 1e-5:
            raise FrontierMeshError("normal is not unit length")
        built.append(
            SurfaceVertex(
                scale_position(local, position_scale),
                normal,
                (uv[0] * uv_scale[0], uv[1] * uv_scale[1]),
                table,
            )
        )
    faces = tuple(
        SurfaceTriangle((remap[a], remap[b], remap[c]), material)
        for a, b, c, material in triangles
    )
    mesh = SurfaceMesh(tuple(built), faces)
    for vertex in mesh.vertices:
        total = math.fsum(entry.weight for entry in vertex.weights)
        if not math.isfinite(total) or abs(total - 1.0) > WEIGHT_SUM_EPSILON:
            raise FrontierMeshError("weight table does not sum to 1")
        for component in (vertex.position.x, vertex.position.y, vertex.position.z, vertex.uv[0], vertex.uv[1]):
            if not math.isfinite(component):
                raise FrontierMeshError("non-finite coordinate")
    return mesh


def _finish(
    source: SurfaceMesh,
    geometry: SurfaceMesh,
    *,
    face_budget: int,
    uv_scale: tuple[float, float],
    position_scale: float,
    allowed_bones: frozenset[str] | None,
) -> MeshLod:
    positions, triangles = _collapse_to_budget(geometry, face_budget)
    mesh = _assemble(
        source,
        geometry,
        positions,
        triangles,
        uv_scale=uv_scale,
        position_scale=position_scale,
        allowed_bones=allowed_bones,
    )
    if mesh.face_count > face_budget:
        raise FrontierMeshError("face budget unreachable")
    reference = source if position_scale == 1.0 else _reference_mesh(source, position_scale)
    hausdorff = directed_hausdorff([vertex.position for vertex in mesh.vertices], reference)
    seam_delta = seam_position_delta(mesh)
    if seam_delta > SEAM_POSITION_EPSILON + 1e-9:
        raise FrontierMeshError("seam position diverged")
    return MeshLod(
        mesh=mesh,
        face_budget=face_budget,
        hausdorff_max=hausdorff,
        seam_position_delta=seam_delta,
        vertex_digest=vertex_digest(mesh),
    )


def _require_budget(face_budget: object, *, default: int | None = None) -> int:
    if face_budget is None and default is not None:
        face_budget = default
    if type(face_budget) is not int or isinstance(face_budget, bool) or face_budget < 1:
        raise FrontierMeshError("face budget must be a positive integer")
    return face_budget


def simplify_lod(mesh: SurfaceMesh, face_budget: int) -> MeshLod:
    """Collapse ``mesh`` until it has at most ``face_budget`` triangles.

    Output weights are barycentric samples of the original surface, renormalized
    to 1. The vertex digest is a pure function of the source and the budget.
    """
    if not isinstance(mesh, SurfaceMesh):
        raise FrontierMeshError("surface mesh required")
    budget = _require_budget(face_budget)
    return _finish(
        mesh,
        mesh,
        face_budget=budget,
        uv_scale=(1.0, 1.0),
        position_scale=1.0,
        allowed_bones=None,
    )


def retarget(
    source: SurfaceMesh,
    *,
    uv_scale: tuple[float, float],
    position_scale: float = 1.0,
    face_budget: int | None = None,
    target_bones: Sequence[str] | None = None,
    target_mesh: SurfaceMesh | None = None,
) -> MeshLod:
    """Retarget ``source`` onto a bone subset and optional target topology.

    Positions are multiplied by ``position_scale``. Normals are returned at
    unit length and flip when ``position_scale`` is negative. Texture
    coordinates are multiplied by ``uv_scale``. When ``target_mesh`` is
    omitted, the source topology is the destination and ``face_budget``
    collapses it. When ``target_mesh`` is present, that mesh is the
    destination (also collapsed when a budget is set) and its bone names
    must be a subset of the source. Skin weights always come from the closest
    point on the source, restricted to the target bone names, then
    renormalized to 1.

    The same source, target, scales, and budget produce the same vertex digest.
    """
    if not isinstance(source, SurfaceMesh):
        raise FrontierMeshError("surface mesh required")
    if target_mesh is not None and not isinstance(target_mesh, SurfaceMesh):
        raise FrontierMeshError("surface mesh required")
    scale = _positive_scale(position_scale)
    texture_scale = _uv_scale(uv_scale)
    declared = _bone_argument(target_bones)
    if target_mesh is None and declared is None:
        raise FrontierMeshError("target bone names are not a subset of the source")
    if declared is not None:
        assert_bone_subset(declared, source)
    if target_mesh is not None:
        assert_bone_subset(bone_names(target_mesh), source)
        if declared is None:
            declared = bone_names(target_mesh)
    geometry = source if target_mesh is None else target_mesh
    budget = _require_budget(face_budget, default=geometry.face_count)
    return _finish(
        source,
        geometry,
        face_budget=budget,
        uv_scale=texture_scale,
        position_scale=scale,
        allowed_bones=declared,
    )

