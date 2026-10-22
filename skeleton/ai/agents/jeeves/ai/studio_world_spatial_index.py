"""Source-owned world-space descriptors for *placed* 3D assets.

Conservative bounding spheres are calculated from actual compiled glTF
accessor bounds. Placement transforms, physics, LOD and semantic ancestry
must agree with the authored scene receipt and byte-replayed asset catalog.
The bounds are broad-phase search data, NOT an observed collision shape.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from math import ceil, isqrt
from typing import Any
import json
import re

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.original_world_spatial_index.v1"
MAX_WORLD_INSTANCES = 128
MAX_BYTES = 512 * 1024
VALID_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class WorldSpatialIndexError(ValueError):
    """Scene-instance descriptor cannot be traced to real reviewed asset bytes."""


def _json(value: Any) -> bytes:
    try:
        raw = json.dumps(
            value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise WorldSpatialIndexError("spatial descriptor cannot be finite JSON") from exc
    if len(raw) > MAX_BYTES:
        raise WorldSpatialIndexError("spatial index exceeds bounded source budget")
    return raw


def _hash(value: Any) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise WorldSpatialIndexError("spatial ancestry requires an SHA-256")
    return value


def _vec(value: Any, length: int, min_value: int,
         max_value: int) -> list[int]:
    if (type(value) is not list or len(value) != length
            or any(type(x) is not int or not min_value <= x <= max_value
                   for x in value)):
        raise WorldSpatialIndexError("authored world transform exceeds finite bounds")
    return list(value)


def _radius_from_glb_metrics(metrics: Mapping[str, Any]) -> int:
    """Ceiled AABB-corner distance conservatively encloses arbitrary rotations."""
    if not isinstance(metrics, Mapping):
        raise WorldSpatialIndexError("missing byte-replayed GLB bounds")
    lower, upper = metrics.get("bounds_min_m"), metrics.get("bounds_max_m")
    if (type(lower) is not list or type(upper) is not list
            or len(lower) != 3 or len(upper) != 3):
        raise WorldSpatialIndexError("invalid original glTF position bounds")
    dimensions: list[int] = []
    for low, high in zip(lower, upper, strict=True):
        if (type(low) not in (int, float) or type(high) not in (int, float)
                or not -1000 <= low <= high <= 1000):
            raise WorldSpatialIndexError("mesh bounds are not measured finite meters")
        dimensions.append(ceil(max(abs(low), abs(high)) * 1000))
    square = sum(value * value for value in dimensions)
    radial = isqrt(square)
    return max(1, radial + (square > radial * radial))


def compile_world_spatial_index(
    *, project_id: str, source_head_sha256: str | None,
    catalog: Mapping[str, Any], placements: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile a deterministic spatial manifest from verified scene and assets."""
    if type(project_id) is not str or not 1 <= len(project_id) <= 128:
        raise WorldSpatialIndexError("spatial index needs a project identity")
    if source_head_sha256 is not None:
        _hash(source_head_sha256)
    if not isinstance(catalog, Mapping) or not isinstance(placements, Mapping):
        raise WorldSpatialIndexError("spatial assets need a source-owned catalog")
    from .studio_asset_descriptors import (
        CATALOG_SCHEMA, catalog_bytes,
    )
    if (catalog.get("schema_version") != CATALOG_SCHEMA
            or catalog.get("project_id") != project_id
            or catalog.get("source_head_sha256") != source_head_sha256):
        raise WorldSpatialIndexError("asset catalog source head differs from scene")
    unsealed = dict(catalog)
    seal = unsealed.pop("receipt_sha256", None)
    if seal != sha256(_json(unsealed)).hexdigest():
        raise WorldSpatialIndexError("catalog was not content-addressed")
    asset_hash = sha256(catalog_bytes(catalog)).hexdigest()
    parts = dict(placements)
    signature = parts.pop("receipt_sha256", None)
    if signature != digest(parts):
        raise WorldSpatialIndexError("original placed scene source is unsealed")
    originals = placements.get("instances")
    if (type(originals) is not list or len(originals) > MAX_WORLD_INSTANCES
            or placements.get("instance_count") != len(originals)):
        raise WorldSpatialIndexError("authored placed scene exceeds finite bounds")
    assets = {}
    for candidate in catalog.get("descriptors", []):
        key = (candidate.get("kind"), candidate.get("asset_id"))
        if key in assets:
            raise WorldSpatialIndexError("ambiguous original asset ID")
        assets[key] = candidate
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in originals:
        if not isinstance(source, Mapping):
            raise WorldSpatialIndexError("world instance source malformed")
        instance_id, asset_id = source.get("instance_id"), source.get("asset_id")
        if (type(instance_id) is not str
                or VALID_ID.fullmatch(instance_id) is None
                or type(asset_id) is not str or VALID_ID.fullmatch(asset_id) is None
                or instance_id in seen):
            raise WorldSpatialIndexError("world instance identity must be unique")
        seen.add(instance_id)
        asset = assets.get(("procedural_mesh", asset_id))
        if asset is None:
            raise WorldSpatialIndexError("placed object references uncompiled GLB")
        if (_hash(asset["source_sha256"]) != source.get("base_source_sha256")
                or _hash(asset["content_sha256"]) != source.get("glb_sha256")
                or asset["source_record_id"] != source.get("base_record_id")
                or asset["source_compiler_receipt_sha256"] is None):
            raise WorldSpatialIndexError("placement points to a different source mesh")
        position = _vec(source.get("position_mm"), 3, -10_000_000, 10_000_000)
        angles = _vec(source.get("rotation_deg"), 3, -360, 360)
        scale = source.get("scale_per_mille")
        if type(scale) is not int or not 100 <= scale <= 10000:
            raise WorldSpatialIndexError("source scale must be positive and bounded")
        kind = source.get("visual_or_physics")
        actual_physics = asset["metrics"].get("physics")
        actual_lod = (
            any(
                item.get("kind") == "procedural_mesh"
                and item.get("metrics", {}).get("lod", {}).get("parent_asset_id")
                == asset_id
                for item in catalog["descriptors"]
            )
        )
        if (kind not in ("visual", "physics", "lod")
                or (kind == "physics" and not isinstance(actual_physics, Mapping))
                or (kind == "lod" and not actual_lod)
                or (kind == "visual" and actual_lod)
                or (kind == "physics") != (source.get("physics_record_id") is not None)
                or (kind == "physics" and source["physics_record_id"] !=
                    actual_physics["physics_source_record_id"])):
            raise WorldSpatialIndexError("scene instance visual, LOD and collider mismatch")
        path = "game/frontier/meshes/" + asset_id + (
            ".physics.tscn" if kind == "physics"
            else ".lod.tscn" if kind == "lod"
            else ".tscn"
        )
        if source.get("resource_path") != path:
            raise WorldSpatialIndexError("world instance points to a foreign scene")
        raw_radius = _radius_from_glb_metrics(asset["metrics"])
        radius = (raw_radius * scale + 999) // 1000
        entry = {
            "instance_id": instance_id,
            "asset_id": asset_id,
            "kind": kind,
            "scene_resource_path": path,
            "source_record_id": source["author_record_id"],
            "source_sha256": _hash(source["author_source_sha256"]),
            "source_mesh_sha256": asset["source_sha256"],
            "mesh_glb_sha256": asset["content_sha256"],
            "parent_asset_descriptor_sha256": _hash(asset["receipt_sha256"]),
            "position_mm": position,
            "rotation_deg": angles,
            "scale_per_mille": scale,
            "conservative_radius_mm": radius,
            "broadphase_aabb_min_mm": [value - radius for value in position],
            "broadphase_aabb_max_mm": [value + radius for value in position],
            "physics_source_record_id": source.get("physics_record_id"),
            "physics_body_type": (
                actual_physics["body_type"] if kind == "physics" else None
            ),
            "authored_lod_available": actual_lod,
            "title": asset["title"],
            "tags": list(asset["tags"]),
            "roles": list(asset["roles"]),
            "bounds_are_conservative_not_engine_contact_geometry": True,
        }
        entry["receipt_sha256"] = digest(entry)
        entries.append(entry)
    entries.sort(key=lambda item: item["instance_id"])
    index = {
        "schema_version": SCHEMA,
        "project_id": project_id,
        "source_head_sha256": source_head_sha256,
        "parent_asset_catalog_sha256": asset_hash,
        "source_placement_receipt_sha256": signature,
        "instance_count": len(entries),
        "instances": entries,
        "coordinate_units": "millimeters",
        "query_bounds": "conservative_bounding_sphere_AABB",
        "actual_native_scene_import_observed": False,
        "actual_collision_contacts_observed": False,
    }
    index["receipt_sha256"] = digest(index)
    _json(index)
    return index


def spatial_index_bytes(index: Mapping[str, Any]) -> bytes:
    return _json(index)


def verify_world_spatial_index(
    raw: bytes, *, project_id: str, source_head_sha256: str | None,
    catalog: Mapping[str, Any], placements: Mapping[str, Any],
) -> dict[str, Any]:
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise WorldSpatialIndexError("world spatial catalog is not bounded bytes")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WorldSpatialIndexError("world spatial index is invalid JSON") from exc
    if type(parsed) is not dict or _json(parsed) != raw:
        raise WorldSpatialIndexError("world index source JSON was not canonical")
    replay = compile_world_spatial_index(
        project_id=project_id, source_head_sha256=source_head_sha256,
        catalog=catalog, placements=placements,
    )
    if parsed != replay:
        raise WorldSpatialIndexError(
            "published spatial bounds/descriptors differ from source-verified scene"
        )
    return {
        "schema_version": "skeleton.jeeves.original_world_spatial_replay.v1",
        "world_index_sha256": sha256(raw).hexdigest(),
        "scene_instances_replayed": replay["instance_count"],
        "source_scene_and_binary_asset_receipts_replayed": True,
        "native_3d_scene_visibility_observed": False,
    }


def query_world_spatial_index(
    index: Mapping[str, Any], *, center_mm: list[int],
    radius_mm: int, limit: int = 12,
    kind: str | None = None,
) -> dict[str, Any]:
    """A bounded spatial AABB candidate retrieval, NOT a hit/collision claim."""
    center = _vec(center_mm, 3, -10_000_000, 10_000_000)
    if (type(radius_mm) is not int or not 0 <= radius_mm <= 10_000_000
            or type(limit) is not int or not 1 <= limit <= 32
            or kind not in (None, "visual", "lod", "physics")):
        raise WorldSpatialIndexError("spatial query must be bounded")
    if (not isinstance(index, Mapping)
            or index.get("schema_version") != SCHEMA
            or type(index.get("instances")) is not list
            or len(index["instances"]) > MAX_WORLD_INSTANCES):
        raise WorldSpatialIndexError("spatial query needs compiled index")
    contents = dict(index)
    proof = contents.pop("receipt_sha256", None)
    if proof != digest(contents):
        raise WorldSpatialIndexError("spatial lookup index is not sealed")
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for item in index["instances"]:
        if kind is not None and item.get("kind") != kind:
            continue
        low, high = item["broadphase_aabb_min_mm"], item["broadphase_aabb_max_mm"]
        squared = sum(
            (max(low[i] - center[i], center[i] - high[i], 0)) ** 2
            for i in range(3)
        )
        if squared <= radius_mm * radius_mm:
            mid = item["position_mm"]
            distance = sum((mid[i] - center[i]) ** 2 for i in range(3))
            scored.append((distance, item["instance_id"], item))
    scored.sort(key=lambda entry: (entry[0], entry[1]))
    selected = [item for _, _, item in scored[:limit]]
    return {
        "schema_version": "skeleton.jeeves.original_world_spatial_query.v1",
        "source_index_receipt_sha256": proof,
        "source_head_sha256": index["source_head_sha256"],
        "matches": len(scored),
        "instances": selected,
        "result_receipt_sha256": digest(selected),
        "native_collision_or_visibility_verified": False,
    }


__all__ = [
    "WorldSpatialIndexError", "compile_world_spatial_index",
    "verify_world_spatial_index", "spatial_index_bytes",
    "query_world_spatial_index",
]
