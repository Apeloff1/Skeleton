"""Deterministic Godot 4 mesh importer wrappers and runtime LOD scenes.

The compiled .tscn file instantiates each imported glTF PackedScene correctly.
The optional scripted LOD wrapper instantiates the authored source GLBs and
switches by true 3D camera distance with hysteresis. Scene text is generated
and independently byte-compared, never confused with a native import receipt.
"""
from __future__ import annotations

from typing import Any

from collections.abc import Mapping
from hashlib import sha256
import re

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.mesh_godot_preview.v1"
ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class OriginalMeshGodotError(ValueError):
    """Godot source wrapper does not match original typed GLB identity."""


def _identity(metadata: Mapping[str, Any], directory: str) -> str:
    if not isinstance(metadata, Mapping):
        raise OriginalMeshGodotError("Godot mesh preview needs actual compiler metadata")
    body = dict(metadata)
    proof = body.pop("receipt_sha256", None)
    name = metadata.get("asset_id")
    if (proof != digest(body)
            or metadata.get("schema_version") !=
            "skeleton.jeeves.original_mesh_glb.v1"
            or type(name) is not str or ID.fullmatch(name) is None
            or type(metadata.get("glb_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", metadata["glb_sha256"]) is None
            or directory != "game/frontier/meshes"):
        raise OriginalMeshGodotError("Godot mesh wrapper lost a reviewed GLB receipt")
    return name


def compile_mesh_godot_resources(
    metadata: Mapping[str, Any], *,
    directory: str = "game/frontier/meshes",
    lod_manifest: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Source-authored, importable GLB scene and optional runtime LOD control."""
    asset = _identity(metadata, directory)
    path = directory + "/" + asset
    if lod_manifest is not None:
        manifest = dict(lod_manifest)
        seal = manifest.pop("receipt_sha256", None)
        if (seal != digest(manifest)
                or lod_manifest.get("schema_version") !=
                "skeleton.jeeves.original_mesh_lod_set.v1"
                or lod_manifest.get("asset_id") != asset
                or lod_manifest.get("base_glb_sha256") != metadata["glb_sha256"]
                or lod_manifest.get("native_import_executed") is not False
                or lod_manifest.get("runtime_lod_switching_observed") is not False):
            raise OriginalMeshGodotError("LOD scene differs from source-owned GLBs")
    scene = "\n".join([
        "[gd_scene load_steps=2 format=3]",
        "",
        '[ext_resource type="PackedScene" path="res://' + path + '.glb" id="1"]',
        "",
        '[node name="OriginalMesh" type="Node3D"]',
        "",
        '[node name="ImportedGeometry" parent="." instance=ExtResource("1")]',
        "",
    ])
    files = {path + ".tscn": scene}
    if lod_manifest is not None:
        levels = lod_manifest.get("levels")
        if (type(levels) is not list or not 1 <= len(levels) <= 4
                or any(type(entry) is not dict
                       or entry.get("level") != i + 1
                       or type(entry.get("switch_distance_mm")) is not int
                       or type(entry.get("glb_sha256")) is not str
                       for i, entry in enumerate(levels))):
            raise OriginalMeshGodotError("LOD scene requires sequential exact levels")
        paths = [path + ".glb"] + [
            path + ".lod" + str(item["level"]) + ".glb" for item in levels
        ]
        distances = [item["switch_distance_mm"] / 1000.0 for item in levels]
        # Literal paths and float array content are derived ONLY from validated
        # source IDs and bounded source millimeter distances, never injected
        # from arbitrary model-generated scripts or filesystem names.
        gdscript = "\n".join([
            "extends Node3D",
            "",
            "const ORIGINAL_MESH_PATHS = ["
            + ", ".join('"' + "res://" + path + '"' for path in paths) + "]",
            "const ORIGINAL_SWITCH_METERS = [" + ", ".join(
                format(value, ".3f") for value in distances
            ) + "]",
            "",
            "var _sources: Array[PackedScene] = []",
            "var _active_level: int = -1",
            "var _instanced_mesh: Node3D",
            "",
            "func _ready() -> void:",
            "    for resource_path in ORIGINAL_MESH_PATHS:",
            "        var resource := load(resource_path)",
            "        if not (resource is PackedScene):",
            '            push_error("Original Jeeves GLB import unavailable: " + resource_path)',
            "            set_process(false)",
            "            return",
            "        _sources.append(resource)",
            "    _show_level(0)",
            "",
            "func _process(_delta: float) -> void:",
            "    var camera := get_viewport().get_camera_3d()",
            "    if camera == null or _active_level < 0:",
            "        return",
            "    var distance := camera.global_position.distance_to(global_position)",
            "    var target := _active_level",
            "    # Hysteresis prevents rapid scene reloads at LOD boundaries.",
            "    while target < ORIGINAL_SWITCH_METERS.size() and distance >= "
            + "ORIGINAL_SWITCH_METERS[target] + 0.25:",
            "        target += 1",
            "    while target > 0 and distance < "
            + "ORIGINAL_SWITCH_METERS[target - 1] - 0.25:",
            "        target -= 1",
            "    if target != _active_level:",
            "        _show_level(target)",
            "",
            "func _show_level(level: int) -> void:",
            "    if level < 0 or level >= _sources.size():",
            "        return",
            "    var instance := _sources[level].instantiate()",
            "    if not (instance is Node3D):",
            '        push_error("Imported mesh root must be a Node3D")',
            "        return",
            "    if _instanced_mesh != null:",
            "        remove_child(_instanced_mesh)",
            "        _instanced_mesh.queue_free()",
            "    _instanced_mesh = instance",
            "    add_child(_instanced_mesh)",
            "    _active_level = level",
            "",
        ])
        scene_lod = "\n".join([
            "[gd_scene load_steps=2 format=3]",
            "",
            '[ext_resource type="Script" path="res://' + path + '.lod.gd" id="1"]',
            "",
            '[node name="OriginalMeshLOD" type="Node3D"]',
            'script = ExtResource("1")',
            "",
        ])
        files[path + ".lod.gd"] = gdscript
        files[path + ".lod.tscn"] = scene_lod
    return files


def verify_mesh_godot_resources(
    metadata: Mapping[str, Any], files: Mapping[str, str], *,
    directory: str = "game/frontier/meshes",
    lod_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = compile_mesh_godot_resources(
        metadata, directory=directory, lod_manifest=lod_manifest,
    )
    if (not isinstance(files, Mapping) or dict(files) != expected
            or any(type(x) is not str for x in files.values())):
        raise OriginalMeshGodotError("Godot mesh scene/script differs from source GLB")
    receipt = {
        "schema_version": SCHEMA,
        "glb_sha256": metadata["glb_sha256"],
        "resources": {
            name: sha256(body.encode("utf-8")).hexdigest()
            for name, body in sorted(expected.items())
        },
        "lod_levels": len(lod_manifest["levels"]) if lod_manifest else 0,
        "source_text_reproducible": True,
        "engine_scene_instantiated": False,
        "rendered_framerate_or_lod_switch_observed": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


__all__ = [
    "OriginalMeshGodotError", "compile_mesh_godot_resources",
    "verify_mesh_godot_resources",
]
