"""Independent published Godot game-root mesh instance attestation.

Source-owned original actors are not counted as game world instances until
the published expedition.tscn actually links the child scene and its
PackedScene entries to the reviewed GLB, LOD or physics scene.
"""
from __future__ import annotations

from typing import Any

from collections.abc import Mapping
from hashlib import sha256
from zipfile import ZipFile

from .studio_original_mesh_placements import (
    OriginalMeshPlacementError, PLACEMENT_SCENE, PLACEMENT_SOURCE, ROOT_SCENE,
    verify_original_mesh_placement_source_bundle,
)
from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCENE


class OriginalMeshPlacementArchiveError(ValueError):
    """An exported game scene cannot be replayed from approved mesh placements."""


def verify_original_mesh_placement_archive(
    archive: ZipFile, file_hashes: Mapping[str, str],
    proof: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(proof, Mapping) or not isinstance(file_hashes, Mapping):
        raise OriginalMeshPlacementArchiveError("game mesh authority missing")
    metadata = proof.get("packaged_original_mesh_placements")
    if not isinstance(metadata, dict):
        raise OriginalMeshPlacementArchiveError("mesh instance manifest missing")
    from .studio_interaction_contract import digest
    claim = dict(metadata)
    seal = claim.pop("receipt_sha256", None)
    if seal != digest(claim):
        raise OriginalMeshPlacementArchiveError("mesh instance receipt altered")
    entries = metadata.get("instances")
    if (type(entries) is not list or len(entries) > 128
            or metadata.get("instance_count") != len(entries)):
        raise OriginalMeshPlacementArchiveError(
            "mesh instance count is not bounded or consistent"
        )
    root = archive.read(ROOT_SCENE).decode("utf-8")
    present_scene = PLACEMENT_SCENE in file_hashes
    present_source = PLACEMENT_SOURCE in file_hashes
    if present_scene != present_source or present_scene != bool(entries):
        raise OriginalMeshPlacementArchiveError(
            "source-owned mesh placement scene or original source is absent"
        )
    if not entries:
        if root != _GODOT_SCENE:
            raise OriginalMeshPlacementArchiveError(
                "unreviewed replacement to the real game world scene"
            )
        return {
            "schema_version": "skeleton.jeeves.original_mesh_placement_archive.v1",
            "instances_replayed": 0,
            "root_scene_sha256": sha256(root.encode("utf-8")).hexdigest(),
            "real_scene_hierarchy_compiled": False,
            "native_gameplay_observed": False,
        }
    expected_lod = frozenset(
        item["asset_id"]
        for item in proof.get("packaged_original_mesh_lods", [])
    )
    expected_physics = frozenset(
        item["asset_id"]
        for item in proof.get("packaged_original_mesh_physics", [])
    )
    try:
        verified = verify_original_mesh_placement_source_bundle(
            archive.read(PLACEMENT_SOURCE),
            published_scene=archive.read(PLACEMENT_SCENE).decode("utf-8"),
            published_root=root,
            expected_lod_asset_ids=expected_lod,
            expected_physics_asset_ids=expected_physics,
        )
    except (OriginalMeshPlacementError, ValueError, KeyError,
            TypeError, UnicodeDecodeError) as exc:
        raise OriginalMeshPlacementArchiveError(
            "published mesh world instances differ from source-governed scene"
        ) from exc
    if (verified["instances_replayed"] != len(entries)
            or verified["scene_sha256"] != metadata["placement_scene_sha256"]):
        raise OriginalMeshPlacementArchiveError(
            "mesh instance catalogue differs from published game hierarchy"
        )
    return {
        "schema_version": "skeleton.jeeves.original_mesh_placement_archive.v1",
        "instances_replayed": verified["instances_replayed"],
        "root_scene_sha256": verified["root_sha256"],
        "real_scene_hierarchy_compiled": True,
        "native_gameplay_observed": False,
    }


__all__ = [
    "OriginalMeshPlacementArchiveError",
    "verify_original_mesh_placement_archive",
]
