"""Read-only recovery and reconciliation of independently pinned migrated progress.

This path never creates a game, modifies a save, deletes a failed installation
or infers an atomic transaction from two independently durable publications.
"""
from __future__ import annotations

import hmac
from pathlib import Path

from skeleton.ai.game_builder.dual_runtime_verify import (
    load_verified_playable_world, verify_exported_package,
)
from skeleton.ai.game_builder.playable_simulation import deserialize_replay
from skeleton.app.offline_delivery_archive import inspect_offline_game_archive
from skeleton.app.private_game_save import read_private_game_save


SCHEMA = "skeleton.app.offline_progress_reconciliation.v1"


class OfflineProgressReconciliationError(ValueError):
    """Independent source, archive or save custody failed reconciliation."""


def reconcile_migrated_offline_progress(
    installed_source: str | Path, private_save: str | Path, *,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    authorized: bool,
    archive: str | Path | None = None,
    expected_archive_sha256: str | None = None,
) -> dict[str, object]:
    """Reexecute saved actions against an independently pinned installed world.

    An optional original ZIP must be supplied together with its own pin. Its
    integrity is checked twice. Source and save are also checked before and
    after replay; the operation makes no claims about prior migration
    atomicity, executable package signatures or device runtime coverage.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if (archive is None) != (expected_archive_sha256 is None):
        raise OfflineProgressReconciliationError(
            "archive reconciliation requires archive and independent pin"
        )
    archive_before = None
    if archive is not None:
        archive_before = inspect_offline_game_archive(
            archive, expected_archive_sha256=expected_archive_sha256,
            expected_manifest_sha256=expected_manifest_sha256, authorized=True,
        )
    before = verify_exported_package(
        installed_source, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    world = load_verified_playable_world(
        installed_source, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    saved = read_private_game_save(
        private_save, expected_sha256=expected_save_sha256, authorized=True,
    )
    replay = deserialize_replay(world, saved, authorized=True)
    # Re-read the same owner-private, single-link inode by its name. The
    # underlying reader checks descriptor identity and the external digest.
    saved_after = read_private_game_save(
        private_save, expected_sha256=expected_save_sha256, authorized=True,
    )
    if not hmac.compare_digest(saved, saved_after):
        raise OfflineProgressReconciliationError(
            "private replay changed during reconciliation"
        )
    replay_after = deserialize_replay(world, saved_after, authorized=True)
    after = verify_exported_package(
        installed_source, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (before != after or after.get("world_digest") != world.digest
            or replay.digest != replay_after.digest
            or after.get("offline_gameplay_reexecuted") is not True):
        raise OfflineProgressReconciliationError(
            "installed game or replay changed during reconciliation"
        )
    if archive_before is not None:
        archive_after = inspect_offline_game_archive(
            archive, expected_archive_sha256=expected_archive_sha256,
            expected_manifest_sha256=expected_manifest_sha256, authorized=True,
        )
        if archive_before != archive_after:
            raise OfflineProgressReconciliationError(
                "original source archive changed during reconciliation"
            )
    return {
        "schema": SCHEMA,
        "status": "migrated_source_and_progress_reconciled_release_blocked",
        "project_id": world.intent.project_id,
        "manifest_sha256": expected_manifest_sha256,
        "save_sha256": expected_save_sha256,
        "archive_sha256": expected_archive_sha256,
        "world_digest": world.digest,
        "replay_digest": replay.digest,
        "action_count": len(replay.action_receipts),
        "final_state": replay.final_state.to_payload(),
        "installed_source_replayed": True,
        "private_save_replayed": True,
        "original_archive_integrity_verified": archive_before is not None,
        "read_only": True,
        "migration_atomicity_proven": False,
        "model_inference_observed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


__all__ = [
    "SCHEMA", "OfflineProgressReconciliationError",
    "reconcile_migrated_offline_progress",
]
