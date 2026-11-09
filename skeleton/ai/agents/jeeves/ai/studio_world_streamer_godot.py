"""Reusable opt-in Godot 4 large-world source streamer for original GLB scenes.

Godot code consumes only the two content-addressed, independently verified
source catalogs, and instantiates actual authored PackedScene resources.
Existing static world scenes remain unchanged: this component must be
explicitly instanced in place of static authored meshes, never alongside them.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256

from .studio_interaction_contract import digest
from .studio_world_chunks import (
    WorldChunkError, compile_world_chunk_catalog,
)

SCHEMA = "skeleton.jeeves.world_godot_streaming_source.v1"
GD_PATH = "game/frontier/assets/world_streamer.gd"
SCENE_PATH = "game/frontier/assets/world_streamer.tscn"


class WorldGodotStreamingError(ValueError):
    """Original Godot streaming code or source catalog is not reproducible."""


def compile_godot_world_streamer(
    index: Mapping[str, Any], chunk_catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Generate a reusable, inert-until-instantiated runtime chunk node."""
    if not isinstance(index, Mapping) or not isinstance(chunk_catalog, Mapping):
        raise WorldGodotStreamingError("streaming source needs both authored catalogs")
    try:
        if compile_world_chunk_catalog(index) != chunk_catalog:
            raise WorldGodotStreamingError(
                "streaming code cannot target forged or stale source chunks"
            )
    except WorldChunkError as exc:
        raise WorldGodotStreamingError(
            "streaming source index lacks source ownership"
        ) from exc
    script = "\n".join([
        "extends Node3D",
        "# Original Jeeves source-owned game-world streamer.",
        "# Instantiate ONLY instead of the game's static OriginalMeshInstances.",
        "# Source compilation and SHA checks happen before Godot export.",
        "# This script does not claim GPU residency, collision contacts or FPS.",
        "",
        "@export_range(1.0, 5000.0, 1.0) var view_radius_m: float = 128.0",
        "@export_range(1, 32, 1) var instantiate_per_frame: int = 4",
        "@export_range(1, 32, 1) var release_per_frame: int = 8",
        "const CELL_MM: int = 64000",
        'const WORLD_INDEX: String = "res://game/frontier/assets/world-index.json"',
        'const CHUNK_INDEX: String = "res://game/frontier/assets/world-chunks.json"',
        "",
        "var _world: Dictionary = {}",
        "var _chunks: Dictionary = {}",
        "var _instance_sources: Dictionary = {}",
        "var _loaded: Dictionary = {}",
        "var _last_frame_instantiated: int = 0",
        "var _last_frame_released: int = 0",
        "var _total_instantiated: int = 0",
        "var _total_released: int = 0",
        "",
        "func _load_catalog(path: String) -> Dictionary:",
        "    var file := FileAccess.open(path, FileAccess.READ)",
        "    if file == null:",
        '        push_error("Jeeves world streamer missing source: " + path)',
        "        return {}",
        "    var parsed = JSON.parse_string(file.get_as_text())",
        "    if not (parsed is Dictionary):",
        '        push_error("Jeeves world streamer invalid JSON: " + path)',
        "        return {}",
        "    return parsed",
        "",
        "func _ready() -> void:",
        "    _world = _load_catalog(WORLD_INDEX)",
        "    _chunks = _load_catalog(CHUNK_INDEX)",
        '    if _world.get("schema_version", "") != "skeleton.jeeves.original_world_spatial_index.v1":',
        '        push_error("Jeeves world streamer has unsupported world index schema")',
        "        set_process(false)",
        "        return",
        '    if _chunks.get("schema_version", "") != "skeleton.jeeves.world_chunk_catalog.v1":',
        '        push_error("Jeeves world streamer has unsupported chunk schema")',
        "        set_process(false)",
        "        return",
        '    if _chunks.get("source_world_receipt_sha256", "") != _world.get("receipt_sha256", ""):',
        '        push_error("Jeeves world streamer refused mismatched source revisions")',
        "        set_process(false)",
        "        return",
        '    for item in _world.get("instances", []):',
        "        if not (item is Dictionary):",
        "            set_process(false)",
        "            return",
        '        var ident := str(item.get("instance_id", ""))',
        "        if ident.is_empty() or _instance_sources.has(ident):",
        '            push_error("Jeeves world streamer duplicate original scene ID")',
        "            set_process(false)",
        "            return",
        "        _instance_sources[ident] = item",
        "",
        "func _vec_mm(parts: Array) -> Vector3:",
        "    return Vector3(float(parts[0]), float(parts[1]), float(parts[2])) / 1000.0",
        "",
        "func _process(_delta: float) -> void:",
        "    _last_frame_instantiated = 0",
        "    _last_frame_released = 0",
        "    var camera := get_viewport().get_camera_3d()",
        "    if camera == null:",
        "        return",
        "    var camera_mm := camera.global_position * 1000.0",
        '    var max_extent := float(_chunks.get("max_instance_radius_mm", 0))',
        "    var search_mm: float = view_radius_m * 1000.0 + max_extent",
        "    var low := Vector3i(",
        "        floori((camera_mm.x - search_mm) / CELL_MM),",
        "        floori((camera_mm.y - search_mm) / CELL_MM),",
        "        floori((camera_mm.z - search_mm) / CELL_MM)",
        "    )",
        "    var high := Vector3i(",
        "        floori((camera_mm.x + search_mm) / CELL_MM),",
        "        floori((camera_mm.y + search_mm) / CELL_MM),",
        "        floori((camera_mm.z + search_mm) / CELL_MM)",
        "    )",
        "    var relevant: Dictionary = {}",
        '    for home in _chunks.get("chunks", []):',
        "        var parts := str(home.get(\"cell\", \"\")).split(\",\")",
        "        if parts.size() != 3:",
        "            continue",
        "        var cell := Vector3i(int(parts[0]), int(parts[1]), int(parts[2]))",
        "        if cell.x < low.x or cell.x > high.x:",
        "            continue",
        "        if cell.y < low.y or cell.y > high.y:",
        "            continue",
        "        if cell.z < low.z or cell.z > high.z:",
        "            continue",
        '        for ident in home.get("instance_ids", []):',
        "            var key := str(ident)",
        "            if not _instance_sources.has(key):",
        "                continue",
        "            var item: Dictionary = _instance_sources[key]",
        '            var center: Vector3 = _vec_mm(item["position_mm"])',
        '            var radius: float = float(item["conservative_radius_mm"]) / 1000.0',
        "            # Conservative bounding-sphere test, not a precise hitbox.",
        "            if center.distance_to(camera.global_position) <= view_radius_m + radius:",
        "                relevant[key] = item",
        "    # Stateful rigid bodies and trigger areas must never be unloaded",
        "    # solely because the observer camera leaves the source chunk.",
        "    for key in _instance_sources.keys():",
        "        var pinned_item: Dictionary = _instance_sources[key]",
        '        if pinned_item.get("kind", "") == "physics" and str(pinned_item.get("physics_body_type", "")) in ["rigid", "area"]:',
        "            relevant[key] = pinned_item",
        "    var pending_release := release_per_frame",
        "    for name in _loaded.keys():",
        "        if relevant.has(name):",
        "            continue",
        "        if pending_release <= 0:",
        "            break",
        "        var node: Node3D = _loaded[name]",
        "        _loaded.erase(name)",
        "        node.queue_free()",
        "        pending_release -= 1",
        "        _last_frame_released += 1",
        "        _total_released += 1",
        "    var wanted := relevant.keys()",
        "    # Deterministic priority by nearest source center, then unique ID.",
        "    wanted.sort_custom(func(a, b):",
        '        var a_pin: bool = str(relevant[a].get("physics_body_type", "")) in ["rigid", "area"]',
        '        var b_pin: bool = str(relevant[b].get("physics_body_type", "")) in ["rigid", "area"]',
        "        if a_pin != b_pin:",
        "            return a_pin",
        '        var pa: Vector3 = _vec_mm(relevant[a]["position_mm"])',
        '        var pb: Vector3 = _vec_mm(relevant[b]["position_mm"])',
        "        var da: float = pa.distance_squared_to(camera.global_position)",
        "        var db: float = pb.distance_squared_to(camera.global_position)",
        "        " + 'return da < db if da != db else str(a) < str(b)',
        "    )",
        "    var pending := instantiate_per_frame",
        "    for name in wanted:",
        "        if _loaded.has(name) or pending <= 0:",
        "            continue",
        "        var item: Dictionary = relevant[name]",
        '        var resource_path := str(item.get("scene_resource_path", ""))',
        '        if not resource_path.begins_with("game/frontier/meshes/"):',
        '            push_error("Jeeves source contains unauthorized mesh scene")',
        "            continue",
        '        if not resource_path.ends_with(".tscn"):',
        "            continue",
        '        var resource := load("res://" + resource_path)',
        "        if not (resource is PackedScene):",
        '            push_error("Original compiled 3D scene did not import: " + resource_path)',
        "            continue",
        "        var node := resource.instantiate()",
        "        if not (node is Node3D):",
        '            push_error("Original 3D asset is not a Node3D")',
        "            node.queue_free()",
        "            continue",
        "        node.name = str(name)",
        '        node.position = _vec_mm(item["position_mm"])',
        '        var angles: Array = item["rotation_deg"]',
        "        node.rotation_degrees = Vector3(float(angles[0]), float(angles[1]), float(angles[2]))",
        '        node.scale = Vector3.ONE * (float(item["scale_per_mille"]) / 1000.0)',
        "        add_child(node)",
        "        _loaded[name] = node",
        "        pending -= 1",
        "        _last_frame_instantiated += 1",
        "        _total_instantiated += 1",
        "",
    ])
    scene = "\n".join([
        "[gd_scene load_steps=2 format=3]",
        "",
        '[ext_resource type="Script" path="res://' + GD_PATH + '" id="1"]',
        "",
        '[node name="OriginalWorldStreamer" type="Node3D"]',
        'script = ExtResource("1")',
        "",
    ])
    files = {GD_PATH: script, SCENE_PATH: scene}
    receipt = {
        "schema_version": SCHEMA,
        "world_index_receipt_sha256": index["receipt_sha256"],
        "chunk_catalog_receipt_sha256": chunk_catalog["receipt_sha256"],
        "resources": {
            name: sha256(data.encode("utf-8")).hexdigest()
            for name, data in sorted(files.items())
        },
        "static_world_scene_preserved": True,
        "streamer_requires_explicit_instantiation": True,
        "per_frame_scene_instantiation_budget": 4,
        "per_frame_scene_release_budget": 8,
        "native_frame_counters_available": True,
        "stateful_rigid_and_area_instance_pinning": True,
        "source_runtime_streaming_executed": False,
        "resource_residency_observed": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return {"files": files, "receipt": receipt}


def verify_godot_world_streamer(
    index: Mapping[str, Any], chunk_catalog: Mapping[str, Any],
    files: Mapping[str, str], receipt: Mapping[str, Any],
) -> dict[str, Any]:
    expected = compile_godot_world_streamer(index, chunk_catalog)
    if (not isinstance(files, Mapping)
            or not isinstance(receipt, Mapping)
            or dict(files) != expected["files"]
            or dict(receipt) != expected["receipt"]):
        raise WorldGodotStreamingError(
            "Godot world streamer script, scene or source receipt altered"
        )
    return {
        "schema_version": "skeleton.jeeves.world_godot_streamer_replay.v1",
        "files_checked": len(files),
        "streamer_receipt_sha256": receipt["receipt_sha256"],
        "source_text_reproduced": True,
        "native_streaming_executed": False,
    }


__all__ = [
    "WorldGodotStreamingError", "compile_godot_world_streamer",
    "verify_godot_world_streamer",
]
