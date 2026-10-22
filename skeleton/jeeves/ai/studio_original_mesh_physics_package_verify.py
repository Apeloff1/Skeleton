"""Independent ZIP-layer physics/body attestation from original mesh sources.

All scene text, collider vertices, physical material, density-derived mass,
layers/masks and render-link selection must reproduce from the archived
author source and the actual previously-validated GLB and LOD inventory.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any
from zipfile import ZipFile

from .studio_original_mesh_physics import (
    OriginalMeshPhysicsError, verify_original_mesh_physics,
)


class OriginalMeshPhysicsArchiveError(ValueError):
    """A published Godot physics source/shape cannot replay its original mesh."""


def verify_original_mesh_physics_archive(
    archive: ZipFile, file_hashes: Mapping[str, str],
    proof: Mapping[str, Any], meshes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    authored = proof.get("packaged_original_mesh_physics")
    if (type(authored) is not list or len(authored) > 64
            or proof.get("native_collision_physics_verified") is not False):
        raise OriginalMeshPhysicsArchiveError(
            "packaged physics inventory or engine claims invalid"
        )
    mesh_index = {}
    for mesh in meshes:
        info = mesh.get("metadata") if isinstance(mesh, Mapping) else None
        if not isinstance(info, Mapping) or info.get("asset_id") in mesh_index:
            raise OriginalMeshPhysicsArchiveError("physics mesh inventory ambiguous")
        mesh_index[info["asset_id"]] = info
    seen = set()
    results = []
    for candidate in authored:
        if (type(candidate) is not dict or set(candidate) != {
                "asset_id", "base_glb_sha256", "source_record_id",
                "source_sha256", "scene_sha256", "metadata_receipt_sha256",
                "lod_bound",
        }):
            raise OriginalMeshPhysicsArchiveError("physics receipt fields incomplete")
        asset = candidate["asset_id"]
        if type(asset) is not str or asset in seen or asset not in mesh_index:
            raise OriginalMeshPhysicsArchiveError(
                "physics source references a duplicate or missing GLB"
            )
        seen.add(asset)
        root = "game/frontier/meshes/" + asset
        scene_path, source_path = root + ".physics.tscn", root + ".physics.source.json"
        if scene_path not in file_hashes or source_path not in file_hashes:
            raise OriginalMeshPhysicsArchiveError(
                "original collider scene or its source omitted from ZIP"
            )
        try:
            source = json.loads(archive.read(source_path))
            if type(source) is not dict or set(source) != {
                    "base_record", "author_record", "metadata",
            }:
                raise OriginalMeshPhysicsError("original physics source malformed")
            original = source["base_record"]
            author = source["author_record"]
            metadata = source["metadata"]
            scene = archive.read(scene_path).decode("utf-8")
            checked = verify_original_mesh_physics(
                original, author, scene, metadata,
                has_lod=candidate["lod_bound"],
            )
        except (OriginalMeshPhysicsError, ValueError, TypeError,
                KeyError, UnicodeDecodeError) as exc:
            raise OriginalMeshPhysicsArchiveError(
                "Godot collider or physical properties differ from original source"
            ) from exc
        lod_render = root + ".lod.tscn"
        if (metadata["lod_bound"] != (lod_render in file_hashes)
                or metadata["lod_bound"] is not candidate["lod_bound"]):
            raise OriginalMeshPhysicsArchiveError(
                "collider visual scene does not reference actual authored LOD"
            )
        if (metadata["mesh_glb_sha256"] !=
                mesh_index[asset]["glb_sha256"]
                or candidate["base_glb_sha256"] !=
                mesh_index[asset]["glb_sha256"]
                or candidate["source_record_id"] != author["record_id"]
                or candidate["source_sha256"] != author["source_sha256"]
                or candidate["scene_sha256"] != checked["scene_sha256"]
                or candidate["metadata_receipt_sha256"] !=
                checked["source_receipt_sha256"]):
            raise OriginalMeshPhysicsArchiveError(
                "collision body was substituted across source revisions"
            )
        results.append({
            "asset_id": asset,
            "scene_sha256": checked["scene_sha256"],
            "original_physics_source_sha256": author["source_sha256"],
            "physics_receipt_sha256": metadata["receipt_sha256"],
            "body_type": metadata["body_type"],
            "collider_shape": metadata["collider"]["shape"],
            "lod_bound": metadata["lod_bound"],
        })
    expected_physics_files = {
        "game/frontier/meshes/" + item["asset_id"] + suffix
        for item in authored
        for suffix in (".physics.tscn", ".physics.source.json")
    }
    actual_physics_files = {
        path for path in file_hashes
        if path.startswith("game/frontier/meshes/")
        and path.endswith((".physics.tscn", ".physics.source.json"))
    }
    if actual_physics_files != expected_physics_files:
        raise OriginalMeshPhysicsArchiveError(
            "extra unsigned collision script or source in Godot ZIP"
        )
    return {
        "schema_version": "skeleton.jeeves.original_mesh_physics_archive_replay.v1",
        "bodies_replayed": len(results),
        "static_bodies": sum(r["body_type"] == "static" for r in results),
        "rigid_bodies": sum(r["body_type"] == "rigid" for r in results),
        "trigger_areas": sum(r["body_type"] == "area" for r in results),
        "verified_physics_receipts": results,
        "collider_source_replayed": True,
        "native_contact_or_trigger_event_observed": False,
    }


__all__ = [
    "OriginalMeshPhysicsArchiveError",
    "verify_original_mesh_physics_archive",
]
