"""Reviewed, source-bound parametric 3D level-of-detail compiler.

Each LOD is independently reconstructed using the existing original GLB
compiler at an explicitly authored segmentation level. LODs are neither
unreviewed decimations nor a claim that a target engine switched them.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from .studio_interaction_contract import digest
from .studio_original_mesh import (
    OriginalMeshError, _source, compile_original_mesh, verify_original_mesh,
)

SCHEMA = "skeleton.jeeves.original_mesh_lod_set.v1"
DOC_KEYS = frozenset({"kind", "base_record_id", "asset_id", "levels"})
LEVEL_KEYS = frozenset({"level", "segments", "switch_distance_mm"})
MAX_LOD_LEVELS = 4
MAX_LOD_SETS = 64


class OriginalMeshLodError(ValueError):
    """LOD source, geometry, or distance policy is not independently justified."""


def _check(base: Mapping[str, Any], author: Mapping[str, Any]) -> list[dict[str, int]]:
    if not isinstance(base, Mapping) or not isinstance(author, Mapping):
        raise OriginalMeshLodError("LOD requires original and authored records")
    try:
        primitive = _source(base)
    except OriginalMeshError as exc:
        raise OriginalMeshLodError("LOD base is not an original valid GLB source") from exc
    if primitive["primitive"] not in ("cylinder", "uv_sphere"):
        raise OriginalMeshLodError(
            "only radially tessellated mesh primitives support source LOD"
        )
    if (author.get("facet") != "asset_forge"
            or type(author.get("document")) is not dict
            or set(author["document"]) != DOC_KEYS):
        raise OriginalMeshLodError("LOD requires a complete asset_forge source")
    doc = author["document"]
    if (doc["kind"] != "procedural_mesh_lod_set"
            or doc["base_record_id"] != base["record_id"]
            or doc["asset_id"] != primitive["asset_id"]):
        raise OriginalMeshLodError("LOD does not identify its original mesh")
    rid = author.get("record_id")
    dependencies = author.get("depends_on")
    version = author.get("revision")
    if (type(rid) is not str or not rid
            or type(version) is not int or not 1 <= version <= 1_000_000
            or type(dependencies) is not list
            or len(dependencies) > 32
            or base["record_id"] not in dependencies
            or len(set(dependencies)) != len(dependencies)
            or any(type(x) is not str for x in dependencies)
            or author.get("source_sha256") != digest([
                rid, "asset_forge", version, doc, dependencies,
            ])):
        raise OriginalMeshLodError("LOD record lacks exact original revision ancestry")
    levels = doc["levels"]
    if (type(levels) is not list
            or not 1 <= len(levels) <= MAX_LOD_LEVELS
            or len(primitive["asset_id"]) > 59):
        raise OriginalMeshLodError("LOD set or derived asset IDs exceed bounds")
    before_segments = primitive["segments"]
    before_distance = 0
    checked: list[dict[str, int]] = []
    for index, level in enumerate(levels, 1):
        if type(level) is not dict or set(level) != LEVEL_KEYS:
            raise OriginalMeshLodError("LOD level requires exact author controls")
        number, segments, distance = (
            level["level"], level["segments"], level["switch_distance_mm"],
        )
        if (type(number) is not int or number != index
                or type(segments) is not int
                or not 6 <= segments < before_segments
                or type(distance) is not int
                or not 1000 <= distance <= 10_000_000
                or distance <= before_distance + 250):
            raise OriginalMeshLodError(
                "LOD segmentation must decrease and switch distance must increase"
            )
        checked.append(dict(level))
        before_segments, before_distance = segments, distance
    return checked


def _derive(base: Mapping[str, Any], author: Mapping[str, Any],
            index: int, segments: int) -> dict[str, Any]:
    doc = dict(base["document"])
    doc["asset_id"] = doc["asset_id"] + "-lod" + str(index)
    doc["segments"] = segments
    # The virtual revision is content-addressed to BOTH real source records;
    # it cannot be mistaken for a persisted primary author document.
    virtual_id = "lod-" + sha256((
        base["source_sha256"] + author["source_sha256"] + str(index)
    ).encode("ascii")).hexdigest()[:32]
    deps = [base["record_id"], author["record_id"]]
    virtual = {
        "record_id": virtual_id, "facet": "asset_forge",
        "revision": 1, "document": doc, "depends_on": deps,
    }
    virtual["source_sha256"] = digest([
        virtual_id, "asset_forge", 1, doc, deps,
    ])
    return virtual


def compile_original_mesh_lod_set(
    base: Mapping[str, Any], authored: Mapping[str, Any],
) -> dict[str, Any]:
    """Build original GLB and every derived lower-detail GLB deterministically."""
    levels = _check(base, authored)
    parent = compile_original_mesh(base)
    outputs = []
    previous_triangles = parent["metadata"]["triangles"]
    for entry in levels:
        virtual = _derive(base, authored, entry["level"], entry["segments"])
        compiled = compile_original_mesh(virtual)
        proof = verify_original_mesh(
            virtual, compiled["glb"], compiled["metadata"],
        )
        triangles = proof["triangles"]
        if triangles >= previous_triangles or triangles < 1:
            raise OriginalMeshLodError(
                "authored LOD did not actually reduce original indexed geometry"
            )
        previous_triangles = triangles
        outputs.append({
            "level": entry["level"], "segments": entry["segments"],
            "switch_distance_mm": entry["switch_distance_mm"],
            "derived_record": virtual,
            "glb": compiled["glb"],
            "metadata": compiled["metadata"],
        })
    proof = {
        "schema_version": SCHEMA,
        "asset_id": base["document"]["asset_id"],
        "original_record_id": base["record_id"],
        "original_source_sha256": base["source_sha256"],
        "author_record_id": authored["record_id"],
        "author_source_sha256": authored["source_sha256"],
        "base_glb_sha256": parent["metadata"]["glb_sha256"],
        "base_vertices": parent["metadata"]["vertices"],
        "base_triangles": parent["metadata"]["triangles"],
        "levels": [{
            "level": entry["level"],
            "segments": entry["segments"],
            "switch_distance_mm": entry["switch_distance_mm"],
            "derived_record_sha256": entry["derived_record"]["source_sha256"],
            "glb_sha256": entry["metadata"]["glb_sha256"],
            "compiler_receipt_sha256": entry["metadata"]["receipt_sha256"],
            "vertices": entry["metadata"]["vertices"],
            "triangles": entry["metadata"]["triangles"],
        } for entry in outputs],
        "derived_from_reviewed_parametric_sources": True,
        "unreviewed_mesh_decimation_performed": False,
        "native_import_executed": False,
        "runtime_lod_switching_observed": False,
    }
    proof["receipt_sha256"] = digest(proof)
    return {"manifest": proof, "base": parent, "levels": outputs}


def verify_original_mesh_lod_set(
    base: Mapping[str, Any], author: Mapping[str, Any],
    manifest: Mapping[str, Any], glbs: Mapping[str, bytes],
) -> dict[str, Any]:
    """Regenerate every GLB and receipt from separate original source records."""
    replay = compile_original_mesh_lod_set(base, author)
    if not isinstance(manifest, Mapping) or dict(manifest) != replay["manifest"]:
        raise OriginalMeshLodError("LOD chain manifest differs from approved source")
    expected = {
        entry["metadata"]["asset_id"]: entry["glb"]
        for entry in replay["levels"]
    }
    if (not isinstance(glbs, Mapping)
            or set(glbs) != set(expected)
            or any(glbs[key] != val for key, val in expected.items())):
        raise OriginalMeshLodError("published LOD GLB bytes diverge from original source")
    return {
        "schema_version": "skeleton.jeeves.original_mesh_lod_replay.v1",
        "asset_id": replay["manifest"]["asset_id"],
        "levels_replayed": len(expected),
        "source_lod_receipt_sha256": replay["manifest"]["receipt_sha256"],
        "all_geometry_bytes_and_distances_replayed": True,
        "engine_lod_switch_observed": False,
    }


def compile_original_mesh_lod_collection(
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(records, Mapping):
        raise OriginalMeshLodError("LOD collection needs original project sources")
    authored = [
        source for _, source in sorted(records.items())
        if isinstance(source.get("document"), dict)
        and source["document"].get("kind") == "procedural_mesh_lod_set"
    ]
    if len(authored) > MAX_LOD_SETS:
        raise OriginalMeshLodError("LOD graph exceeds finite build budget")
    results = []
    seen: set[str] = set()
    for record in authored:
        base_id = record["document"].get("base_record_id")
        base = records.get(base_id)
        if not isinstance(base, Mapping) or base_id in seen:
            raise OriginalMeshLodError("missing or duplicate LOD base source")
        seen.add(base_id)
        results.append(compile_original_mesh_lod_set(base, record))
    return {
        "schema_version": SCHEMA,
        "count": len(results), "sets": results,
        "native_lod_rendering_verified": False,
    }


__all__ = [
    "OriginalMeshLodError", "compile_original_mesh_lod_set",
    "verify_original_mesh_lod_set", "compile_original_mesh_lod_collection",
]
