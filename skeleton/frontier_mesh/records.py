"""Surface records for deterministic mesh LOD.

``skeleton/mesh`` is the service-mesh package and does not define a vertex.
Jeeves already has the position type and the skinned-mesh records this
package reuses:

* ``Vec3`` and ``SkinnedMesh`` in ``skeleton.jeeves.game_frontier_production``
  (one bone index per vertex, no weights, normals, UVs, or materials)
* ``EraMesh`` in ``skeleton.jeeves.game_frontier_mesh_evolution`` (normals and
  source pixels, no skin weights or materials)

A second vertex layout exists only for the attributes those records do not
carry together: a bone-name weight table, a unit normal, a texture
coordinate, and a per-triangle material. Positions and normals stay ``Vec3``.

Seam rule
---------
``SEAM_POSITION_EPSILON`` is ``1e-6``. Two vertices are seam copies when they
lie within this distance and the group touches two or more materials. Edge
collapse writes one position into every copy, so the two material sides of a
seam match within this epsilon (the measured delta is 0 when the copies
survive as distinct indices).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from skeleton.jeeves.game_frontier_mesh_evolution import EraMesh
from skeleton.jeeves.game_frontier_production import (
    CharacterSkeleton,
    FrontierProductionError,
    SkinnedMesh,
    Vec3,
)

SEAM_POSITION_EPSILON = 1e-6
WEIGHT_SUM_EPSILON = 1e-5
AREA_EPSILON = 1e-10
MAX_VERTICES = 4096
MAX_TRIANGLES = 4096
_DIGEST_SCHEMA = "skeleton.frontier_mesh.vertex.v1"
_VEC3_LIMIT = 1e8


class FrontierMeshError(ValueError):
    """Fail-closed rejection for LOD, transfer, and retarget."""


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FrontierMeshError("non-finite coordinate")
    number = float(value)
    if not math.isfinite(number):
        raise FrontierMeshError("non-finite coordinate")
    return number


def _bounded(value: object) -> float:
    number = _finite(value)
    if abs(number) > _VEC3_LIMIT:
        raise FrontierMeshError("non-finite coordinate")
    return number


def _vec3(value: object) -> Vec3:
    if isinstance(value, Vec3):
        return value
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise FrontierMeshError("non-finite coordinate")
    try:
        return Vec3(_bounded(value[0]), _bounded(value[1]), _bounded(value[2]))
    except FrontierProductionError as exc:
        raise FrontierMeshError("non-finite coordinate") from exc


def _unit(normal: Vec3) -> Vec3:
    length = math.sqrt(normal.dot(normal))
    if length < AREA_EPSILON or not math.isfinite(length):
        raise FrontierMeshError("zero-length normal")
    try:
        return normal.scaled(1.0 / length)
    except FrontierProductionError as exc:
        raise FrontierMeshError("non-finite coordinate") from exc


def _bone_name(name: object) -> str:
    if not isinstance(name, str) or not name or len(name) > 128 or "/" in name:
        raise FrontierMeshError("invalid bone name")
    return name


@dataclass(frozen=True, slots=True)
class SkinWeight:
    bone_name: str
    weight: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "bone_name", _bone_name(self.bone_name))
        weight = _finite(self.weight)
        if weight < 0.0:
            raise FrontierMeshError("weight table does not sum to 1")
        object.__setattr__(self, "weight", weight)


def _check_weights(weights: Sequence[SkinWeight]) -> None:
    if not weights:
        raise FrontierMeshError("weight table does not sum to 1")
    seen: set[str] = set()
    for entry in weights:
        if not isinstance(entry, SkinWeight):
            raise FrontierMeshError("weight table does not sum to 1")
        if entry.bone_name in seen:
            raise FrontierMeshError("duplicate bone name")
        seen.add(entry.bone_name)
    total = math.fsum(entry.weight for entry in weights)
    if not math.isfinite(total) or abs(total - 1.0) > WEIGHT_SUM_EPSILON:
        raise FrontierMeshError("weight table does not sum to 1")


def renormalize(raw: Mapping[str, float]) -> tuple[SkinWeight, ...]:
    """Drop non-positive entries and force the remaining table to sum to 1."""
    items = [
        (_bone_name(name), _finite(weight))
        for name, weight in raw.items()
        if weight > 1e-15
    ]
    items.sort(key=lambda item: item[0])
    total = math.fsum(weight for _, weight in items)
    if not math.isfinite(total) or total <= WEIGHT_SUM_EPSILON:
        raise FrontierMeshError("weight table does not sum to 1")
    if any(weight < 0.0 for _, weight in items):
        raise FrontierMeshError("weight table does not sum to 1")
    scaled = [(name, weight / total) for name, weight in items]
    if len(scaled) == 1:
        scaled = [(scaled[0][0], 1.0)]
    else:
        head = math.fsum(weight for _, weight in scaled[:-1])
        last = 1.0 - head
        if last <= 0.0 or not math.isfinite(last):
            raise FrontierMeshError("weight table does not sum to 1")
        scaled[-1] = (scaled[-1][0], last)
    result = tuple(SkinWeight(name, weight) for name, weight in scaled)
    _check_weights(result)
    return result


@dataclass(frozen=True, slots=True)
class SurfaceVertex:
    position: Vec3
    normal: Vec3
    uv: tuple[float, float]
    weights: tuple[SkinWeight, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.position, Vec3) or not isinstance(self.normal, Vec3):
            raise FrontierMeshError("position and normal must be Vec3")
        if not isinstance(self.uv, tuple) or len(self.uv) != 2:
            raise FrontierMeshError("texture coordinate must be a pair")
        object.__setattr__(self, "uv", (_finite(self.uv[0]), _finite(self.uv[1])))
        length = math.sqrt(self.normal.dot(self.normal))
        if not math.isfinite(length) or abs(length - 1.0) > 1e-5:
            raise FrontierMeshError("normal is not unit length")
        ordered = tuple(sorted(self.weights, key=lambda entry: entry.bone_name))
        object.__setattr__(self, "weights", ordered)
        _check_weights(self.weights)


@dataclass(frozen=True, slots=True)
class SurfaceTriangle:
    indices: tuple[int, int, int]
    material: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.indices, tuple)
            or len(self.indices) != 3
            or any(type(index) is not int for index in self.indices)
        ):
            raise FrontierMeshError("invalid triangle indices")
        if len(set(self.indices)) != 3:
            raise FrontierMeshError("zero-area triangle")
        if not isinstance(self.material, str) or not self.material or len(self.material) > 128:
            raise FrontierMeshError("material name required")


def cross_length(a: Vec3, b: Vec3, c: Vec3) -> float:
    normal = (b - a).cross(c - a)
    return math.sqrt(normal.dot(normal))


def bone_names(mesh: "SurfaceMesh") -> frozenset[str]:
    names: set[str] = set()
    for vertex in mesh.vertices:
        for entry in vertex.weights:
            if entry.weight > 0.0:
                names.add(entry.bone_name)
    return frozenset(names)


def _assert_area(mesh: "SurfaceMesh") -> None:
    for triangle in mesh.triangles:
        a, b, c = (mesh.vertices[index].position for index in triangle.indices)
        length = cross_length(a, b, c)
        if not math.isfinite(length) or length < AREA_EPSILON:
            raise FrontierMeshError("zero-area triangle")


def validate_mesh(mesh: "SurfaceMesh") -> None:
    if not isinstance(mesh.vertices, tuple) or not isinstance(mesh.triangles, tuple):
        raise FrontierMeshError("mesh vertices and triangles must be tuples")
    if not 3 <= len(mesh.vertices) <= MAX_VERTICES:
        raise FrontierMeshError("vertex count out of range")
    if not 1 <= len(mesh.triangles) <= MAX_TRIANGLES:
        raise FrontierMeshError("triangle count out of range")
    limit = len(mesh.vertices)
    for triangle in mesh.triangles:
        if any(index < 0 or index >= limit for index in triangle.indices):
            raise FrontierMeshError("invalid triangle indices")
    _assert_area(mesh)


@dataclass(frozen=True, slots=True)
class SurfaceMesh:
    vertices: tuple[SurfaceVertex, ...]
    triangles: tuple[SurfaceTriangle, ...]

    def __post_init__(self) -> None:
        validate_mesh(self)

    @property
    def face_count(self) -> int:
        return len(self.triangles)


def make_vertex(
    position: object,
    normal: object,
    uv: tuple[float, float],
    weights: Sequence[tuple[str, float] | SkinWeight],
) -> SurfaceVertex:
    parsed: list[SkinWeight] = []
    for entry in weights:
        if isinstance(entry, SkinWeight):
            parsed.append(entry)
        else:
            parsed.append(SkinWeight(_bone_name(entry[0]), _finite(entry[1])))
    point = _vec3(position)
    direction = _unit(_vec3(normal))
    if not isinstance(uv, tuple) or len(uv) != 2:
        raise FrontierMeshError("texture coordinate must be a pair")
    return SurfaceVertex(point, direction, (_finite(uv[0]), _finite(uv[1])), tuple(parsed))


def make_mesh(
    vertices: Sequence[SurfaceVertex],
    triangles: Sequence[tuple[tuple[int, int, int], str] | SurfaceTriangle],
) -> SurfaceMesh:
    faces: list[SurfaceTriangle] = []
    for triangle in triangles:
        if isinstance(triangle, SurfaceTriangle):
            faces.append(triangle)
        else:
            indices, material = triangle
            faces.append(SurfaceTriangle((int(indices[0]), int(indices[1]), int(indices[2])), material))
    return SurfaceMesh(tuple(vertices), tuple(faces))


def _canon(value: float) -> str:
    number = float(value)
    if number == 0.0:
        number = 0.0
    return format(number, ".12g")


def vertex_digest(mesh: SurfaceMesh) -> str:
    """Stable SHA-256 of positions, unit normals, UVs, bone weights, and faces."""
    payload = {
        "schema": _DIGEST_SCHEMA,
        "vertices": [
            {
                "p": [_canon(v.position.x), _canon(v.position.y), _canon(v.position.z)],
                "n": [_canon(v.normal.x), _canon(v.normal.y), _canon(v.normal.z)],
                "uv": [_canon(v.uv[0]), _canon(v.uv[1])],
                "w": [[entry.bone_name, _canon(entry.weight)] for entry in v.weights],
            }
            for v in mesh.vertices
        ],
        "triangles": [
            [triangle.indices[0], triangle.indices[1], triangle.indices[2], triangle.material]
            for triangle in mesh.triangles
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _area_normals(vertices: Sequence[Vec3], triangles: Sequence[tuple[int, int, int]]) -> tuple[Vec3, ...]:
    accum = [[0.0, 0.0, 0.0] for _ in vertices]
    for a, b, c in triangles:
        normal = (vertices[b] - vertices[a]).cross(vertices[c] - vertices[a])
        for index in (a, b, c):
            accum[index][0] += normal.x
            accum[index][1] += normal.y
            accum[index][2] += normal.z
    result: list[Vec3] = []
    for index, (x, y, z) in enumerate(accum):
        if x == 0.0 and y == 0.0 and z == 0.0:
            raise FrontierMeshError("zero-length normal")
        result.append(_unit(Vec3(x, y, z)))
    return tuple(result)


def from_skinned_mesh(
    mesh: SkinnedMesh,
    skeleton: CharacterSkeleton,
    *,
    material: str = "skin",
    face_materials: Sequence[str] | None = None,
) -> SurfaceMesh:
    """Adapt a one-influence ``SkinnedMesh`` into a weighted surface.

    Bone correspondence is the skeleton bone name at ``bone_influences[i]``,
    with weight 1. Texture coordinates are the vertex XY pair. Normals are
    area-weighted face normals.
    """
    if not isinstance(mesh, SkinnedMesh) or not isinstance(skeleton, CharacterSkeleton):
        raise FrontierMeshError("skinned mesh and character skeleton required")
    if len(mesh.vertices) != len(mesh.bone_influences):
        raise FrontierMeshError("missing skin influences")
    if face_materials is None:
        materials = (material,) * len(mesh.triangles)
    else:
        if len(face_materials) != len(mesh.triangles):
            raise FrontierMeshError("material count does not match triangles")
        materials = tuple(face_materials)
    normals = _area_normals(mesh.vertices, mesh.triangles)
    vertices: list[SurfaceVertex] = []
    for point, normal, influence in zip(mesh.vertices, normals, mesh.bone_influences):
        if type(influence) is not int or not 0 <= influence < len(skeleton.bones):
            raise FrontierMeshError("unknown bone")
        vertices.append(
            SurfaceVertex(
                point,
                normal,
                (_finite(point.x), _finite(point.y)),
                (SkinWeight(skeleton.bones[influence].name, 1.0),),
            )
        )
    faces = tuple(
        SurfaceTriangle(face, face_material)
        for face, face_material in zip(mesh.triangles, materials)
    )
    return SurfaceMesh(tuple(vertices), faces)


def from_era_mesh(mesh: EraMesh, *, bone_name: str) -> SurfaceMesh:
    """Adapt an ``EraMesh`` using its normals and source-pixel coordinates.

    The single skin influence is ``bone_name`` at weight 1. Pixel coordinates
    become texture coordinates in the source bitmap's unit square. No image
    bytes are read.
    """
    if not isinstance(mesh, EraMesh):
        raise FrontierMeshError("era mesh required")
    if mesh.source_width < 1 or mesh.source_height < 1:
        raise FrontierMeshError("non-finite coordinate")
    if len(mesh.vertex_normals) != len(mesh.vertices) or len(mesh.source_pixels) != len(mesh.vertices):
        raise FrontierMeshError("era mesh attributes do not match vertices")
    name = _bone_name(bone_name)
    vertices: list[SurfaceVertex] = []
    for point, normal, pixel in zip(mesh.vertices, mesh.vertex_normals, mesh.source_pixels):
        if len(pixel) != 2:
            raise FrontierMeshError("non-finite coordinate")
        uv = (_finite(pixel[0]) / mesh.source_width, _finite(pixel[1]) / mesh.source_height)
        vertices.append(
            SurfaceVertex(point, _unit(normal), uv, (SkinWeight(name, 1.0),))
        )
    faces = tuple(SurfaceTriangle(face, "era") for face in mesh.triangles)
    return SurfaceMesh(tuple(vertices), faces)
