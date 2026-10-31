"""Original parametric 3D mesh compiler: real glTF 2.0 GLB, not a mesh stub.

Reviewed game-source parameters -> triangulated indexed geometry with positions,
vertex normals, UVs and metallic-roughness PBR materials. All output binary
chunks, accessors, lengths and SHA identities are reproducible and independently
checked. No external copyrighted geometry, textures, web sources or native
engine are silently used.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from math import cos, sin, pi, sqrt
import json
import re
import struct
from typing import Any

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.original_mesh_glb.v1"
DOC_KEYS = frozenset({
    "kind", "asset_id", "primitive", "size_mm", "segments", "color_rgba",
    "metallic_per_mille", "roughness_per_mille",
})
ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{8}$")
PRIMITIVES = frozenset({"box", "plane", "cylinder", "uv_sphere"})
MAX_MESHES = 64
MAX_VERTICES = 16384
MAX_TRIANGLES = 32768
MAX_GLB_BYTES = 1024 * 1024


class OriginalMeshError(ValueError):
    """Authored source does not yield a verifiable bounded glTF mesh."""


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise OriginalMeshError(name + " outside parametric geometry bounds")
    return value


def _source(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping) or record.get("facet") != "asset_forge":
        raise OriginalMeshError("parametric mesh requires authored asset_forge record")
    doc = record.get("document")
    if not isinstance(doc, dict) or set(doc) != DOC_KEYS:
        raise OriginalMeshError("parametric 3D mesh source has incomplete schema")
    if (doc["kind"] != "procedural_mesh"
            or type(doc["primitive"]) is not str
            or doc["primitive"] not in PRIMITIVES):
        raise OriginalMeshError("3D primitive is not supported")
    asset = doc["asset_id"]
    if type(asset) is not str or not ID.fullmatch(asset):
        raise OriginalMeshError("mesh asset identity is not portable ASCII")
    dims = doc["size_mm"]
    if (type(dims) is not list or len(dims) != 3
            or any(type(n) is not int or not 1 <= n <= 100000 for n in dims)):
        raise OriginalMeshError("mesh requires three positive millimeter dimensions")
    _integer(doc["segments"], "mesh radial segmentation", 3, 64)
    _integer(doc["metallic_per_mille"], "PBR metallic", 0, 1000)
    _integer(doc["roughness_per_mille"], "PBR roughness", 0, 1000)
    if type(doc["color_rgba"]) is not str or not COLOR.fullmatch(doc["color_rgba"]):
        raise OriginalMeshError("PBR color requires exact #RRGGBBAA")
    rid = record.get("record_id")
    deps = record.get("depends_on")
    version = record.get("revision")
    if (type(rid) is not str or not ID.fullmatch(rid)
            or type(version) is not int or not 1 <= version <= 1_000_000
            or type(deps) is not list or len(deps) > 32
            or len(set(deps)) != len(deps)
            or any(type(d) is not str for d in deps)
            or record.get("source_sha256") != digest([
                rid, "asset_forge", version, doc, deps,
            ])):
        raise OriginalMeshError("mesh loses exact persisted source revision")
    return doc


def _geometry(doc: Mapping[str, Any]) -> tuple[list[tuple[float, ...]], list[int]]:
    sx, sy, sz = [dim / 1000.0 for dim in doc["size_mm"]]
    vertices: list[tuple[float, ...]] = []
    indices: list[int] = []

    def vertex(position: tuple[float, float, float],
               normal: tuple[float, float, float],
               uv: tuple[float, float]) -> int:
        if len(vertices) >= MAX_VERTICES:
            raise OriginalMeshError("mesh exceeds bounded vertex budget")
        vertices.append((*position, *normal, *uv))
        return len(vertices) - 1

    def triangle(a: int, b: int, c: int) -> None:
        va, vb, vc = vertices[a], vertices[b], vertices[c]
        ab = tuple(vb[i] - va[i] for i in range(3))
        ac = tuple(vc[i] - va[i] for i in range(3))
        cross = (ab[1] * ac[2] - ab[2] * ac[1],
                 ab[2] * ac[0] - ab[0] * ac[2],
                 ab[0] * ac[1] - ab[1] * ac[0])
        if sum(x * x for x in cross) <= 1e-30:
            return  # Exact lathe poles deliberately omit degenerate triangles.
        expected = tuple(sum(vertices[v][axis + 3] for v in (a, b, c))
                         for axis in range(3))
        if sum(cross[i] * expected[i] for i in range(3)) < 0:
            b, c = c, b
        indices.extend((a, b, c))
        if len(indices) // 3 > MAX_TRIANGLES:
            raise OriginalMeshError("mesh exceeds triangle budget")

    def quad(center: tuple[float, float, float],
             u: tuple[float, float, float], v: tuple[float, float, float],
             normal: tuple[float, float, float]) -> None:
        points = []
        for a, b, tex in (
            (-1, -1, (0.0, 0.0)), (1, -1, (1.0, 0.0)),
            (1, 1, (1.0, 1.0)), (-1, 1, (0.0, 1.0)),
        ):
            position = tuple(center[i] + a * u[i] / 2 + b * v[i] / 2
                             for i in range(3))
            points.append(vertex(position, normal, tex))
        triangle(points[0], points[1], points[2])
        triangle(points[0], points[2], points[3])

    primitive = doc["primitive"]
    if primitive in ("box", "plane"):
        quad((0, 0, 0), (sx, 0, 0), (0, 0, sz), (0, 1, 0))
        if primitive == "box":
            # Build six truly outward-facing UV seams rather than merging
            # face normals and destroying hard-surface lighting.
            vertices.clear()
            indices.clear()
            quad((sx / 2, 0, 0), (0, sy, 0), (0, 0, sz), (1, 0, 0))
            quad((-sx / 2, 0, 0), (0, 0, sz), (0, sy, 0), (-1, 0, 0))
            quad((0, sy / 2, 0), (0, 0, sz), (sx, 0, 0), (0, 1, 0))
            quad((0, -sy / 2, 0), (sx, 0, 0), (0, 0, sz), (0, -1, 0))
            quad((0, 0, sz / 2), (sx, 0, 0), (0, sy, 0), (0, 0, 1))
            quad((0, 0, -sz / 2), (0, sy, 0), (sx, 0, 0), (0, 0, -1))
    elif primitive == "cylinder":
        n = doc["segments"]
        for side in range(n + 1):
            angle = 2 * pi * side / n
            x, z = cos(angle), sin(angle)
            inv = sqrt((x / sx) ** 2 + (z / sz) ** 2)
            normal = (x / sx / inv, 0.0, z / sz / inv)
            for yy, uv_y in ((-sy / 2, 0.0), (sy / 2, 1.0)):
                vertex((sx * x / 2, yy, sz * z / 2),
                       normal, (side / n, uv_y))
        for side in range(n):
            a = side * 2
            triangle(a, a + 2, a + 1)
            triangle(a + 1, a + 2, a + 3)
        for sign in (-1, 1):
            y = sign * sy / 2
            normal = (0.0, float(sign), 0.0)
            center = vertex((0, y, 0), normal, (0.5, 0.5))
            rim = []
            for side in range(n):
                angle = 2 * pi * side / n
                x, z = cos(angle), sin(angle)
                rim.append(vertex(
                    (x * sx / 2, y, z * sz / 2), normal,
                    (x / 2 + .5, z / 2 + .5),
                ))
            for side in range(n):
                triangle(center, rim[side], rim[(side + 1) % n])
    else:
        n = doc["segments"]
        rings = max(4, n // 2)
        for latitude in range(rings + 1):
            phi = pi * latitude / rings
            for longitude in range(n + 1):
                theta = 2 * pi * longitude / n
                x, y, z = sin(phi) * cos(theta), cos(phi), sin(phi) * sin(theta)
                # Inverse transpose of scale is required for ellipsoid
                # normals. Naively using unit-sphere vectors is incorrect
                # when the three authored axes are different.
                inv = sqrt((x / sx) ** 2 + (y / sy) ** 2 + (z / sz) ** 2)
                normal = (x / sx / inv, y / sy / inv, z / sz / inv)
                vertex((sx * x / 2, sy * y / 2, sz * z / 2),
                       normal, (longitude / n, latitude / rings))
        cols = n + 1
        for row in range(rings):
            for col in range(n):
                a = row * cols + col
                triangle(a, a + 1, a + cols)
                triangle(a + 1, a + cols + 1, a + cols)
    if not vertices or not indices:
        raise OriginalMeshError("authored primitive yielded no usable geometry")
    return vertices, indices


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _glb(record: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    doc = _source(record)
    verts, faces = _geometry(doc)
    if len(verts) > 65535:
        raise OriginalMeshError("indexed source mesh needs 16-bit accessor bounds")
    position = b"".join(struct.pack("<fff", *v[:3]) for v in verts)
    normals = b"".join(struct.pack("<fff", *v[3:6]) for v in verts)
    uv = b"".join(struct.pack("<ff", *v[6:]) for v in verts)
    index = struct.pack("<" + "H" * len(faces), *faces)
    buffers = [position, normals, uv, index]
    offsets = []
    offset = 0
    payload = bytearray()
    for part in buffers:
        offsets.append(offset)
        payload.extend(part)
        payload.extend(bytes((-len(part)) % 4))
        offset = len(payload)
    unpacked = [struct.unpack_from("<fff", position, i * 12)
                for i in range(len(verts))]
    mins = [min(v[i] for v in unpacked) for i in range(3)]
    maxs = [max(v[i] for v in unpacked) for i in range(3)]
    color = [int(doc["color_rgba"][i:i + 2], 16) / 255
             for i in (1, 3, 5, 7)]
    gltf = {
        "asset": {
            "version": "2.0",
            "generator": "Skeleton Jeeves original parametric mesh compiler",
            "extras": {"skeletonJeevesSource": {
                "recordId": record["record_id"],
                "sourceSha256": record["source_sha256"],
                "primitive": doc["primitive"],
            }},
        },
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": doc["asset_id"], "mesh": 0}],
        "meshes": [{"name": doc["asset_id"], "primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
            "indices": 3, "material": 0, "mode": 4,
        }]}],
        "materials": [{
            "name": doc["asset_id"] + "_pbr",
            "pbrMetallicRoughness": {
                "baseColorFactor": color,
                "metallicFactor": doc["metallic_per_mille"] / 1000,
                "roughnessFactor": doc["roughness_per_mille"] / 1000,
            },
            "alphaMode": "BLEND" if color[3] != 1.0 else "OPAQUE",
            "doubleSided": doc["primitive"] == "plane",
        }],
        "accessors": [{
            "bufferView": 0, "componentType": 5126,
            "count": len(verts), "type": "VEC3", "min": mins, "max": maxs,
        }, {
            "bufferView": 1, "componentType": 5126,
            "count": len(verts), "type": "VEC3",
        }, {
            "bufferView": 2, "componentType": 5126,
            "count": len(verts), "type": "VEC2",
        }, {
            "bufferView": 3, "componentType": 5123,
            "count": len(faces), "type": "SCALAR",
        }],
        "bufferViews": [
            {"buffer": 0, "byteOffset": offsets[i], "byteLength": len(part),
             **({"target": 34963} if i == 3 else {"target": 34962})}
            for i, part in enumerate(buffers)
        ],
        "buffers": [{"byteLength": len(payload)}],
    }
    packed_json = _canonical_json(gltf)
    packed_json += b" " * ((-len(packed_json)) % 4)
    length = 12 + 8 + len(packed_json) + 8 + len(payload)
    glb = (
        struct.pack("<4sII", b"glTF", 2, length)
        + struct.pack("<I4s", len(packed_json), b"JSON") + packed_json
        + struct.pack("<I4s", len(payload), b"BIN\x00") + bytes(payload)
    )
    if len(glb) > MAX_GLB_BYTES:
        raise OriginalMeshError("binary mesh artifact exceeds portable GLB budget")
    evidence = {
        "schema_version": SCHEMA,
        "asset_id": doc["asset_id"],
        "primitive": doc["primitive"],
        "source_record_id": record["record_id"],
        "source_revision": record["revision"],
        "source_sha256": record["source_sha256"],
        "glb_sha256": sha256(glb).hexdigest(),
        "binary_geometry_sha256": sha256(bytes(payload)).hexdigest(),
        "vertices": len(verts),
        "triangles": len(faces) // 3,
        "indexed_geometry": True,
        "coordinate_system": "glTF_Y_up_meters",
        "bounds_min_m": mins,
        "bounds_max_m": maxs,
        "mesh_has_uv0": True,
        "mesh_has_normals": True,
        "material_model": "glTF_metallic_roughness",
        "authored_primitive_only": True,
        "godot_native_import_verified": False,
        "rendered_geometry_verified": False,
        "copyright_review_certified": False,
    }
    evidence["receipt_sha256"] = digest(evidence)
    return glb, evidence


def compile_original_mesh(record: Mapping[str, Any]) -> dict[str, Any]:
    glb, metadata = _glb(record)
    verify_original_mesh(record, glb, metadata)
    return {"glb": glb, "metadata": metadata}


def verify_original_mesh(
    record: Mapping[str, Any], glb: bytes, metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay independently with a strict GLB parser AND source reconstruction."""
    _source(record)
    if (not isinstance(glb, bytes) or len(glb) < 64
            or len(glb) > MAX_GLB_BYTES or not isinstance(metadata, Mapping)):
        raise OriginalMeshError("3D source lacks GLB and provenance bytes")
    try:
        magic, version, length = struct.unpack_from("<4sII", glb)
        json_length, json_tag = struct.unpack_from("<I4s", glb, 12)
        binary_at = 20 + json_length
        bin_length, bin_tag = struct.unpack_from("<I4s", glb, binary_at)
        decoded = json.loads(glb[20:binary_at])
        if (magic != b"glTF" or version != 2 or length != len(glb)
                or json_tag != b"JSON" or bin_tag != b"BIN\x00"
                or json_length % 4 or bin_length % 4
                or binary_at + 8 + bin_length != len(glb)
                or decoded["asset"]["version"] != "2.0"
                or decoded["buffers"][0]["byteLength"] != bin_length
                or len(decoded["meshes"]) != 1
                or len(decoded["accessors"]) != 4):
            raise OriginalMeshError("invalid canonical glTF 2.0 binary layout")
    except (ValueError, KeyError, IndexError, TypeError, struct.error) as exc:
        raise OriginalMeshError("GLB header, chunks or binary accessors invalid") from exc
    claim = dict(metadata)
    signature = claim.pop("receipt_sha256", None)
    if signature != digest(claim):
        raise OriginalMeshError("mesh compiler evidence was modified")
    replay, expected = _glb(record)
    if glb != replay or dict(metadata) != expected:
        raise OriginalMeshError("published mesh diverges from independently rebuilt vertices")
    return {
        "schema_version": "skeleton.jeeves.original_mesh_replay.v1",
        "glb_sha256": sha256(glb).hexdigest(),
        "vertices": metadata["vertices"],
        "triangles": metadata["triangles"],
        "glb_buffer_and_index_geometry_replayed": True,
        "native_rendering_performed": False,
    }


def compile_original_mesh_collection(
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    candidates = [record for _, record in sorted(records.items())
                  if isinstance(record.get("document"), dict)
                  and record["document"].get("kind") == "procedural_mesh"]
    if len(candidates) > MAX_MESHES:
        raise OriginalMeshError("mesh forge output exceeds bounded model budget")
    meshes = [compile_original_mesh(record) for record in candidates]
    names = [m["metadata"]["asset_id"] for m in meshes]
    if len(set(names)) != len(names):
        raise OriginalMeshError("3D mesh IDs must be unique")
    return {"schema_version": SCHEMA, "count": len(meshes), "assets": meshes}


__all__ = [
    "OriginalMeshError", "compile_original_mesh",
    "verify_original_mesh", "compile_original_mesh_collection",
]
