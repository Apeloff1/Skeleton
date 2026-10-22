"""Independent archive-layer verifier for source-owned GLB scenes and LODs.

Rebuilds authored LOD variants and scene text *after* opening a published
Godot project ZIP; it never trusts the exporter’s in-memory render state.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any
from zipfile import ZipFile

from .studio_original_mesh import OriginalMeshError
from .studio_original_mesh_lod import (
    OriginalMeshLodError, verify_original_mesh_lod_set,
)
from .studio_original_mesh_godot import (
    OriginalMeshGodotError, verify_mesh_godot_resources,
)


class OriginalMeshArchiveError(ValueError):
    """Archive did not reproduce exact typed GLB scenes and distance policy."""


def verify_original_mesh_archive_resources(
    archive: ZipFile, names: Mapping[str, str],
    proof: Mapping[str, Any], meshes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(proof, Mapping) or not isinstance(names, Mapping):
        raise OriginalMeshArchiveError("LOD verifier requires original archive manifest")
    lods = proof.get("packaged_original_mesh_lods")
    if (type(lods) is not list or len(lods) > 64
            or proof.get("native_mesh_lod_switching_verified") is not False):
        raise OriginalMeshArchiveError("LOD inventory or engine claim invalid")
    lookup: dict[str, dict[str, Any]] = {}
    for item in lods:
        if (type(item) is not dict or set(item) != {
                "asset_id", "source_record_id", "source_sha256",
                "base_glb_sha256", "lod_manifest_sha256", "levels",
                "godot_source_receipt_sha256",
        } or type(item["asset_id"]) is not str
                or item["asset_id"] in lookup):
            raise OriginalMeshArchiveError("LOD asset is duplicated or malformed")
        lookup[item["asset_id"]] = item
    actual_scene_paths: set[str] = set()
    expected_glbs: set[str] = set()
    expected_authored_sources: set[str] = set()
    lod_levels = 0
    reconstructed_lod_sets: list[dict[str, Any]] = []
    for mesh in meshes:
        metadata = mesh.get("metadata") if isinstance(mesh, Mapping) else None
        if not isinstance(metadata, Mapping):
            raise OriginalMeshArchiveError("GLB mesh metadata missing")
        asset = metadata.get("asset_id")
        if type(asset) is not str:
            raise OriginalMeshArchiveError("GLB mesh asset name missing")
        receipt = lookup.pop(asset, None)
        manifest = None
        expected_glbs.add("game/frontier/meshes/" + asset + ".glb")
        expected_authored_sources.add(
            "game/frontier/meshes/" + asset + ".source.json"
        )
        if receipt is not None:
            path = "game/frontier/meshes/" + asset + ".lods.source.json"
            if path not in names:
                raise OriginalMeshArchiveError("LOD authored source file not published")
            expected_authored_sources.add(path)
            try:
                source = json.loads(archive.read(path))
                if type(source) is not dict or set(source) != {
                        "base_record", "author_record", "manifest",
                }:
                    raise OriginalMeshLodError("LOD source record is malformed")
                manifest = source["manifest"]
                glbs = {}
                for level in manifest["levels"]:
                    num = level["level"]
                    name = asset + "-lod" + str(num)
                    filename = (
                        "game/frontier/meshes/" + asset + ".lod"
                        + str(num) + ".glb"
                    )
                    if filename not in names or name in glbs:
                        raise OriginalMeshLodError("LOD binary file missing or duplicate")
                    expected_glbs.add(filename)
                    glbs[name] = archive.read(filename)
                replay = verify_original_mesh_lod_set(
                    source["base_record"], source["author_record"],
                    manifest, glbs,
                )
                if (replay["levels_replayed"] != receipt["levels"]
                        or source["base_record"]["source_sha256"] !=
                        metadata["source_sha256"]
                        or source["author_record"]["record_id"] !=
                        receipt["source_record_id"]
                        or source["author_record"]["source_sha256"] !=
                        receipt["source_sha256"]
                        or manifest["receipt_sha256"] !=
                        receipt["lod_manifest_sha256"]
                        or metadata["glb_sha256"] !=
                        receipt["base_glb_sha256"]):
                    raise OriginalMeshLodError("LOD manifest lost original source ancestry")
            except (OriginalMeshLodError, OriginalMeshError,
                    ValueError, TypeError, KeyError, IndexError) as exc:
                raise OriginalMeshArchiveError(
                    "actual published LODs do not replay source geometry"
                ) from exc
            lod_levels += replay["levels_replayed"]
            from .studio_original_mesh_lod import compile_original_mesh_lod_set
            reconstructed_lod_sets.append(compile_original_mesh_lod_set(
                source["base_record"], source["author_record"],
            ))
        scene_paths = ["game/frontier/meshes/" + asset + ".tscn"]
        if receipt is not None:
            scene_paths.extend([
                "game/frontier/meshes/" + asset + ".lod.gd",
                "game/frontier/meshes/" + asset + ".lod.tscn",
            ])
        if any(path not in names for path in scene_paths):
            raise OriginalMeshArchiveError(
                "original GLB project lacks executable Godot source scenes"
            )
        try:
            checked = verify_mesh_godot_resources(
                metadata, {
                    filename: archive.read(filename).decode("utf-8")
                    for filename in scene_paths
                }, lod_manifest=manifest,
            )
        except (OriginalMeshGodotError, UnicodeDecodeError) as exc:
            raise OriginalMeshArchiveError(
                "Godot imported mesh scene or script differs from generated source"
            ) from exc
        if (receipt is not None and receipt["godot_source_receipt_sha256"]
                != checked["receipt_sha256"]):
            raise OriginalMeshArchiveError("LOD scene source receipt differs")
        actual_scene_paths.update(scene_paths)
    if lookup:
        raise OriginalMeshArchiveError("LOD refers to unshipped GLB base asset")
    # Forbid orphan/unattributed behavior-bearing .gd/.tscn resources in the
    # original mesh directory, even with a self-consistent manifest hash.
    found = {
        path for path in names
        if path.startswith("game/frontier/meshes/")
        and path.endswith((".tscn", ".gd"))
    }
    if found != actual_scene_paths:
        raise OriginalMeshArchiveError("unattributed mesh behavior or scene source")
    observed_glbs = {
        name for name in names if name.startswith("game/frontier/meshes/")
        and name.endswith(".glb")
    }
    observed_sources = {
        name for name in names if name.startswith("game/frontier/meshes/")
        and name.endswith(".source.json")
    }
    if (observed_glbs != expected_glbs
            or observed_sources != expected_authored_sources):
        raise OriginalMeshArchiveError(
            "unattributed or missing published 3D model binary or source"
        )
    return {
        "schema_version": "skeleton.jeeves.mesh_archive_lod_replay.v1",
        "mesh_scenes_replayed": len(meshes),
        "lod_sets_replayed": len(lods),
        "lod_levels_replayed": lod_levels,
        "lod_catalog_sets": reconstructed_lod_sets,
        "native_scene_import_verified": False,
        "native_lod_switching_verified": False,
    }


__all__ = [
    "OriginalMeshArchiveError", "verify_original_mesh_archive_resources",
]
