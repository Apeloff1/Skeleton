"""Deterministic source-owned 3D chunk index and camera asset-loading planner.

Chunk home cells are intentionally conservative: the search expands by the
largest compiled mesh radius, and exact AABB overlap is rechecked before a
scene resource becomes a preload candidate. No claim is made that Godot
streaming, rendering, GPU residency, or physics contact actually happened.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Any

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.world_chunk_catalog.v1"
PLAN_SCHEMA = "skeleton.jeeves.world_chunk_load_plan.v1"
CELL_MM = 64_000
MAX_INSTANCES = 128
MAX_WORLD_CELLS = 128
MAX_INDEX_BYTES = 256 * 1024


class WorldChunkError(ValueError):
    """Large-world chunk sources or incremental resource plans are not verified."""


def _raw(value: Any) -> bytes:
    try:
        body = json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (ValueError, OverflowError, TypeError, RecursionError) as exc:
        raise WorldChunkError("chunk catalog must be finite portable JSON") from exc
    if len(body) > MAX_INDEX_BYTES:
        raise WorldChunkError("chunk catalog exceeds reproducible source budget")
    return body


def _integer(value: Any, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise WorldChunkError(name + " out of bounded millimeter space")
    return value


def _coord(value: Any, name: str, lo: int, hi: int) -> list[int]:
    if (type(value) is not list or len(value) != 3
            or any(type(part) is not int or not lo <= part <= hi
                   for part in value)):
        raise WorldChunkError(name + " needs three bounded integer coordinates")
    return list(value)


def _checked_world(index: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(index, Mapping):
        raise WorldChunkError("world chunking requires real compiled spatial index")
    source = dict(index)
    receipt = source.pop("receipt_sha256", None)
    if (source.get("schema_version") !=
            "skeleton.jeeves.original_world_spatial_index.v1"
            or receipt != digest(source)
            or type(source.get("instances")) is not list
            or not isinstance(source.get("instance_count"), int)
            or source["instance_count"] != len(source["instances"])
            or len(source["instances"]) > MAX_INSTANCES):
        raise WorldChunkError("spatial scene manifest is missing or unsigned")
    observed = set()
    for instance in source["instances"]:
        if not isinstance(instance, Mapping):
            raise WorldChunkError("chunk source is not an authored 3D instance")
        member = dict(instance)
        member_proof = member.pop("receipt_sha256", None)
        ident = instance.get("instance_id")
        if (member_proof != digest(member)
                or type(ident) is not str
                or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", ident) is None
                or ident in observed):
            raise WorldChunkError("spatial instance proof is ambiguous")
        observed.add(ident)
    return source["instances"]


def _cell_id(position: list[int]) -> str:
    return ",".join(str(part // CELL_MM) for part in position)


def compile_world_chunk_catalog(index: Mapping[str, Any]) -> dict[str, Any]:
    """Build a small home-cell map from exact signed spatial placements."""
    instances = _checked_world(index)
    chunks: dict[str, list[str]] = {}
    max_radius = 0
    for instance in instances:
        pos = _coord(instance.get("position_mm"), "instance", -10_000_000,
                     10_000_000)
        radius = _integer(
            instance.get("conservative_radius_mm"),
            "conservative source radius", 1, 10_000_000,
        )
        expected_lo = [value - radius for value in pos]
        expected_hi = [value + radius for value in pos]
        if (instance.get("broadphase_aabb_min_mm") != expected_lo
                or instance.get("broadphase_aabb_max_mm") != expected_hi):
            raise WorldChunkError("world chunk cannot trust changed AABB geometry")
        max_radius = max(max_radius, radius)
        chunks.setdefault(_cell_id(pos), []).append(instance["instance_id"])
    if len(chunks) > MAX_WORLD_CELLS:
        raise WorldChunkError("chunk index has too many home cells")
    entries = [
        {
            "cell": name,
            "instance_ids": sorted(members),
            "instance_count": len(members),
        }
        for name, members in sorted(chunks.items(),
                                  key=lambda item: tuple(
                                      int(x) for x in item[0].split(",")
                                  ))
    ]
    value = {
        "schema_version": SCHEMA,
        "project_id": index["project_id"],
        "source_head_sha256": index["source_head_sha256"],
        "source_world_index_sha256": sha256(_raw(index)).hexdigest(),
        "source_world_receipt_sha256": index["receipt_sha256"],
        "chunk_edge_mm": CELL_MM,
        "max_instance_radius_mm": max_radius,
        "total_instances": len(instances),
        "chunk_count": len(entries),
        "chunks": entries,
        "all_source_instances_accounted_for": True,
        "native_chunk_streaming_observed": False,
    }
    value["receipt_sha256"] = digest(value)
    _raw(value)
    return value


def world_chunk_catalog_bytes(value: Mapping[str, Any]) -> bytes:
    return _raw(value)


def verify_world_chunk_catalog(
    published: bytes, *, source_index: Mapping[str, Any],
) -> dict[str, Any]:
    if type(published) is not bytes or len(published) > MAX_INDEX_BYTES:
        raise WorldChunkError("published chunk catalog is not bounded binary")
    try:
        decoded = json.loads(published)
    except (UnicodeError, ValueError) as exc:
        raise WorldChunkError("published chunk file is not canonical JSON") from exc
    if type(decoded) is not dict or _raw(decoded) != published:
        raise WorldChunkError("chunk source file differs from JSON canonical form")
    replay = compile_world_chunk_catalog(source_index)
    if decoded != replay:
        raise WorldChunkError("published chunk membership differs from source scene")
    return {
        "schema_version": "skeleton.jeeves.world_chunk_replay.v1",
        "source_chunk_sha256": sha256(published).hexdigest(),
        "home_cells_replayed": replay["chunk_count"],
        "original_instances_replayed": replay["total_instances"],
        "chunk_membership_reproduced": True,
        "godot_streaming_executed": False,
    }


def plan_chunk_resources(
    chunk_catalog: Mapping[str, Any], spatial_index: Mapping[str, Any],
    *, camera_mm: list[int], view_radius_mm: int,
    previously_loaded: list[str] | None = None,
    limit: int = 64,
) -> dict[str, Any]:
    """Bounded load/unload proposal, NOT actual host/engine I/O."""
    if (not isinstance(chunk_catalog, Mapping)
            or not isinstance(spatial_index, Mapping)):
        raise WorldChunkError("chunk planner requires both real source manifests")
    check = dict(chunk_catalog)
    receipt = check.pop("receipt_sha256", None)
    if (receipt != digest(check)
            or check.get("schema_version") != SCHEMA
            or check.get("source_world_receipt_sha256")
            != spatial_index.get("receipt_sha256")):
        raise WorldChunkError("chunk catalog belongs to a different source scene")
    # Reproduce all home-cell membership before trusting a request supplied by
    # a client, including one with an internally self-consistent forged hash.
    if compile_world_chunk_catalog(spatial_index) != chunk_catalog:
        raise WorldChunkError("source chunk membership cannot be replayed")
    camera = _coord(camera_mm, "camera", -10_000_000, 10_000_000)
    _integer(view_radius_mm, "camera range", 0, 10_000_000)
    _integer(limit, "resource planning limit", 1, 128)
    if previously_loaded is None:
        previously_loaded = []
    if (type(previously_loaded) is not list or len(previously_loaded) > 128
            or any(type(x) is not str or
                   re.fullmatch(r"game/frontier/meshes/[a-z0-9_-]{1,64}\\."
                                r"(?:tscn|lod\\.tscn|physics\\.tscn)", x)
                   is None for x in previously_loaded)
            or len(set(previously_loaded)) != len(previously_loaded)):
        raise WorldChunkError("previously loaded resource keys are invalid")
    max_radius = chunk_catalog["max_instance_radius_mm"]
    # Expand by largest radius to include offscreen home cells whose large
    # conservative AABB enters the query view. This has false positives but
    # never intentionally ignores the broad-phase candidate extent.
    scan = view_radius_mm + max_radius
    low = [(x - scan) // CELL_MM for x in camera]
    high = [(x + scan) // CELL_MM for x in camera]
    cells = set()
    for home in chunk_catalog["chunks"]:
        coord = [int(x) for x in home["cell"].split(",")]
        if all(low[i] <= coord[i] <= high[i] for i in range(3)):
            cells.update(home["instance_ids"])
    weighted = []
    for item in spatial_index["instances"]:
        if item["instance_id"] not in cells:
            continue
        lo = item["broadphase_aabb_min_mm"]
        hi = item["broadphase_aabb_max_mm"]
        distance_sq = sum(
            max(lo[i] - camera[i], camera[i] - hi[i], 0) ** 2
            for i in range(3)
        )
        if distance_sq <= view_radius_mm * view_radius_mm:
            center_distance = sum(
                (item["position_mm"][i] - camera[i]) ** 2 for i in range(3)
            )
            weighted.append((center_distance, item["instance_id"], item))
    weighted.sort(key=lambda entry: (entry[0], entry[1]))
    selected = [item for _, _, item in weighted[:limit]]
    if len(weighted) > limit:
        truncated = True
    else:
        truncated = False
    desired = sorted({item["scene_resource_path"] for item in selected})
    loaded = set(previously_loaded)
    plan = {
        "schema_version": PLAN_SCHEMA,
        "source_chunk_receipt_sha256": receipt,
        "source_world_index_receipt_sha256": spatial_index["receipt_sha256"],
        "camera_mm": camera,
        "view_radius_mm": view_radius_mm,
        "candidate_instances_in_view": len(weighted),
        "selected_instances": [entry["instance_id"] for entry in selected],
        "selected_instance_receipts": [
            entry["receipt_sha256"] for entry in selected
        ],
        "required_scene_resources": desired,
        "resources_to_load": sorted(set(desired) - loaded),
        "resources_to_release": sorted(loaded - set(desired)),
        "selection_truncated": truncated,
        "actual_resources_loaded": False,
        "actual_native_gpu_residency_observed": False,
    }
    plan["receipt_sha256"] = digest(plan)
    return plan


__all__ = [
    "WorldChunkError", "compile_world_chunk_catalog",
    "world_chunk_catalog_bytes", "verify_world_chunk_catalog",
    "plan_chunk_resources",
]
