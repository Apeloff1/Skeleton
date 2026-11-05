"""Read-only comparison of two independently pinned private offline game saves.

Both histories are fully reexecuted against the same independently pinned
exported world. This is a local source-level gameplay operation, not a native
device qualification, AI inference proof, or consumer release certification.
"""
from __future__ import annotations

from pathlib import Path

from skeleton.ai.game_builder.dual_runtime_verify import (
    load_verified_playable_world, verify_exported_package,
)
from skeleton.ai.game_builder.playable_simulation import (
    deserialize_replay, replay_divergence,
)
from skeleton.app.private_game_save import read_private_game_save


SCHEMA = "skeleton.app.offline_save_comparison.v1"


class OfflineSaveComparisonError(ValueError):
    """The two saves cannot be compared under verified source custody."""


def compare_verified_offline_saves(
    source_directory: str | Path, *, expected_manifest_sha256: str,
    left_save: str | Path, left_sha256: str,
    right_save: str | Path, right_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Compare complete canonical replay histories, never trusting saved state.

    Caller supplies three independent pins (world manifest and two saves).
    The source verifier runs both before and after the comparison. The save
    reader requires descriptor-bound, owner-private, single-link files on
    supported POSIX hosts. No source, save, or receipt is ever written here.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    world = load_verified_playable_world(
        source_directory, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    left_bytes = read_private_game_save(
        left_save, expected_sha256=left_sha256, authorized=True,
    )
    left = deserialize_replay(world, left_bytes, authorized=True)
    right_bytes = read_private_game_save(
        right_save, expected_sha256=right_sha256, authorized=True,
    )
    right = deserialize_replay(world, right_bytes, authorized=True)
    divergence = replay_divergence(world, left, right, authorized=True)

    # A changed world must never produce a success comparison. Neither an
    # independently pinned manifest nor a matching replay digest alone proves
    # that the current exported package is still the original one.
    final = verify_exported_package(
        source_directory, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if final.get("world_digest") != world.digest:
        raise OfflineSaveComparisonError("game source changed during comparison")

    return {
        "schema": SCHEMA,
        "status": "verified_offline_replay_comparison_release_blocked",
        "project_id": world.intent.project_id,
        "manifest_sha256": expected_manifest_sha256,
        "world_digest": world.digest,
        "left_save_sha256": left_sha256,
        "right_save_sha256": right_sha256,
        "left_replay_digest": left.digest,
        "right_replay_digest": right.digest,
        "left_actions": len(left.action_receipts),
        "right_actions": len(right.action_receipts),
        "first_divergent_action_index": divergence,
        "identical_history": divergence is None,
        "left_final_state": left.final_state.to_payload(),
        "right_final_state": right.final_state.to_payload(),
        "source_verified_before_after": True,
        "both_saves_replayed": True,
        "read_only": True,
        "model_inference_observed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "release_certified": False,
    }


__all__ = [
    "SCHEMA", "OfflineSaveComparisonError", "compare_verified_offline_saves",
]
