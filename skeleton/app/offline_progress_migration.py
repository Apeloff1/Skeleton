"""Install a pinned offline game archive and migrate a canonical private replay.

The migration is deliberately fail-closed and non-transactional across two
separate filesystem destinations. An interrupted installation or publication
requires operator quarantine; it never implies a consumer-ready package.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
from pathlib import Path

from skeleton.ai.game_builder.dual_runtime_verify import (
    load_verified_playable_world, verify_exported_package,
)
from skeleton.ai.game_builder.offline_receipt_publication import (
    preflight_receipt_destination,
)
from skeleton.ai.game_builder.playable_simulation import deserialize_replay
from skeleton.app.offline_archive_install import (
    _parent as _install_parent, install_offline_game_source,
)
from skeleton.app.offline_delivery_archive import inspect_offline_game_archive
from skeleton.app.offline_progress_compatibility import (
    _archive_identity, verify_archived_progress_binding,
)
from skeleton.app.offline_delivery_assurance import _save_identity
from skeleton.app.private_game_save import (
    read_private_game_save, publish_private_game_save,
)


SCHEMA = "skeleton.app.offline_progress_migration.v1"


class OfflineProgressMigrationError(ValueError):
    """Pinned offline source and progress could not be migrated safely."""


def _validate_migration_inputs(
    archive: str | Path, destination: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    original_save: str | Path,
    expected_save_sha256: str,
    migrated_save: str | Path,
    authorized: bool,
) -> tuple[bytes, dict[str, object], dict[str, object]]:
    """Read-only admission shared by migration planning and publication."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    source = Path(destination).expanduser().absolute()
    old_save = Path(original_save).expanduser().absolute()
    new_save = Path(migrated_save).expanduser().absolute()
    if old_save == new_save:
        raise OfflineProgressMigrationError("migration requires a distinct new save")
    # Reject an unsafe parent or occupied destination before any publication.
    target, parent_fd = _install_parent(source)
    try:
        import os
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OfflineProgressMigrationError("installation destination occupied")
    finally:
        import os
        os.close(parent_fd)
    preflight_receipt_destination(
        new_save, protected_roots=(source,), authorized=True,
    )
    raw_save = read_private_game_save(
        old_save, expected_sha256=expected_save_sha256, authorized=True,
    )
    inspected = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )

    compatible = verify_archived_progress_binding(
        archive, raw_save, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256, authorized=True,
    )
    return raw_save, inspected, compatible


def preflight_offline_game_migration(
    archive: str | Path, destination: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    original_save: str | Path,
    expected_save_sha256: str,
    migrated_save: str | Path,
    authorized: bool,
) -> dict[str, object]:
    """Check independent pins and destination admission without publication.

    The pinned archive's typed world reexecutes the private save before any
    destination is reserved. Installation independently repeats the replay
    and verifies the installed source. Preflight is never a reservation.
    """
    raw_save, inspected, compatible = _validate_migration_inputs(
        archive, destination,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        original_save=original_save,
        expected_save_sha256=expected_save_sha256,
        migrated_save=migrated_save,
        authorized=authorized,
    )
    return {
        "schema": "skeleton.app.offline_progress_preflight.v1",
        "status": "offline_migration_inputs_pinned_no_publication",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "save_sha256": expected_save_sha256,
        "save_bytes": len(raw_save),
        "archived_files": inspected["archived_files"],
        "archive_integrity_verified": True,
        "private_save_integrity_verified": True,
        "save_world_binding_verified": True,
        "world_digest": compatible["world_digest"],
        "replay_digest": compatible["replay_digest"],
        "action_count": compatible["action_count"],
        "destination_reserved": False,
        "source_installation_verified": False,
        "private_save_replayed": True,
        "source_gameplay_reexecuted_from_archive": False,
        "native_device_qualified": False,
        "release_certified": False,
    }


def migrate_offline_game_progress(
    archive: str | Path, destination: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    original_save: str | Path,
    expected_save_sha256: str,
    migrated_save: str | Path,
    authorized: bool,
) -> dict[str, object]:
    """Reinstall verified original source and replay a private progress history.

    Archive, source manifest and save have *three independent pins*. This
    function never uses a saved state snapshot as authority: it reconstructs
    the canonical world and reexecutes every recorded action. It does not
    delete or overwrite either source or destination. Both published outputs
    are retained for explicit quarantine if a late verification fails.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    # The independent hashes prove bytes, not that a private path retained
    # its original inode across installation. Fence both original inputs.
    original_archive_identity = _archive_identity(archive)
    original_save_identity = _save_identity(original_save)
    raw_save, inspected, compatible = _validate_migration_inputs(
        archive, destination,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        original_save=original_save,
        expected_save_sha256=expected_save_sha256,
        migrated_save=migrated_save,
        authorized=authorized,
    )
    source = Path(destination).expanduser().absolute()
    old_save = Path(original_save).expanduser().absolute()
    new_save = Path(migrated_save).expanduser().absolute()
    # This creates a new private directory and independently replay-verifies
    # its installed source. No rollback is attempted across owner-controlled
    # paths because an adversarial replacement could otherwise be deleted.
    installed = install_offline_game_source(
        archive, source, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    world = load_verified_playable_world(
        source, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    replay = deserialize_replay(world, raw_save, authorized=True)
    if (compatible["world_digest"] != world.digest
            or compatible["replay_digest"] != replay.digest
            or installed.get("world_digest") != world.digest
            or inspected.get("archive_integrity_verified") is not True
            or installed.get("source_installation_verified") is not True):
        raise OfflineProgressMigrationError("installed world identity is unqualified")
    # A pinned original save must still exist unchanged immediately before
    # publication. The new save is an independently named, no-clobber file.
    reread = read_private_game_save(
        old_save, expected_sha256=expected_save_sha256, authorized=True,
    )
    if not hmac.compare_digest(raw_save, reread):
        raise OfflineProgressMigrationError("original progress changed during migration")
    if (original_archive_identity != _archive_identity(archive)
            or original_save_identity != _save_identity(old_save)):
        raise OfflineProgressMigrationError(
            "original archive or progress inode replaced before save publication"
        )
    new_pin = publish_private_game_save(
        raw_save, new_save, protected_roots=(source,), authorized=True,
    )
    migrated = read_private_game_save(
        new_save, expected_sha256=new_pin, authorized=True,
    )
    if not hmac.compare_digest(raw_save, migrated):
        raise OfflineProgressMigrationError("migrated progress bytes changed")
    replay_after = deserialize_replay(world, migrated, authorized=True)
    if replay_after.digest != replay.digest:
        raise OfflineProgressMigrationError("migrated replay changed after publication")
    final = verify_exported_package(
        source, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    archive_after = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    if (original_archive_identity != _archive_identity(archive)
            or original_save_identity != _save_identity(old_save)):
        raise OfflineProgressMigrationError(
            "original archive or progress inode replaced during migration"
        )
    if (final.get("world_digest") != world.digest
            or final.get("offline_gameplay_reexecuted") is not True
            or archive_after.get("archive_integrity_verified") is not True
            or not hmac.compare_digest(sha256(migrated).hexdigest(), new_pin)):
        raise OfflineProgressMigrationError("source or archive changed during migration")
    return {
        "schema": SCHEMA,
        "status": "offline_progress_migrated_source_replayed_release_blocked",
        "project_id": world.intent.project_id,
        "install_directory": str(source),
        "save_file": str(new_save),
        "manifest_sha256": expected_manifest_sha256,
        "archive_sha256": expected_archive_sha256,
        "original_save_sha256": expected_save_sha256,
        "independent_migrated_save_sha256": new_pin,
        "world_digest": world.digest,
        "replay_digest": replay.digest,
        "action_count": len(replay.action_receipts),
        "final_state": replay.final_state.to_payload(),
        "source_installation_verified": True,
        "archive_integrity_verified": True,
        "private_save_replayed": True,
        "offline_gameplay_reexecuted": True,
        "migration_atomic_across_destinations": False,
        "model_inference_observed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


__all__ = ["SCHEMA", "OfflineProgressMigrationError", "preflight_offline_game_migration", "migrate_offline_game_progress"]
