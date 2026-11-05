"""Signature-first, fail-closed migration of a playable offline game and save.

This is not a transaction across filesystem destinations. On a late failure,
newly published artifacts remain quarantinable; no rollback or release claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from skeleton.app.offline_archive_signature import (
    _pin, _read_detached_file, verify_offline_source_archive_signature,
)
from skeleton.app.offline_delivery_assurance import _save_identity
from skeleton.app.offline_progress_compatibility import _archive_identity
from skeleton.app.offline_progress_migration import (
    migrate_offline_game_progress, preflight_offline_game_migration,
)
from skeleton.app.offline_signed_delivery import assure_signed_offline_delivery

SCHEMA = "skeleton.app.signed_offline_progress_migration.v1"


class SignedOfflineProgressMigrationError(ValueError):
    """Signed archive and private progress cannot be migrated together."""


def _input_identities(
    archive: str | Path, save: str | Path,
    public_key: str | Path, signature: str | Path,
) -> tuple[object, ...]:
    """Pin original input inodes, including detached signature material."""
    return (
        _archive_identity(archive),
        _save_identity(save),
        _read_detached_file(public_key, length=32)[1],
        _read_detached_file(signature, length=64)[1],
    )


def preflight_signed_offline_progress(
    archive: str | Path, destination: str | Path,
    original_save: str | Path, migrated_save: str | Path,
    public_key_file: str | Path, signature_file: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Read-only signature, archive/save compatibility and destination preflight.

    No output is reserved. This receipt is a point-in-time observation, never
    a lease or permission to skip validation at publication time.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, value in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("save", expected_save_sha256),
        ("public key", expected_public_key_sha256),
    ):
        _pin(value, name)
    before = _input_identities(
        archive, original_save, public_key_file, signature_file,
    )
    signed = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    plan = preflight_offline_game_migration(
        archive, destination,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        original_save=original_save,
        expected_save_sha256=expected_save_sha256,
        migrated_save=migrated_save,
        authorized=True,
    )
    if (
        before != _input_identities(
            archive, original_save, public_key_file, signature_file,
        )
        or signed.get("source_archive_signature_verified") is not True
        or signed.get("archive_sha256") != expected_archive_sha256
        or signed.get("manifest_sha256") != expected_manifest_sha256
        or signed.get("public_key_sha256") != expected_public_key_sha256
        or plan.get("save_world_binding_verified") is not True
        or plan.get("destination_reserved") is not False
        or plan.get("release_certified") is not False
    ):
        raise SignedOfflineProgressMigrationError(
            "signed progress preflight changed or did not qualify"
        )
    return {
        "schema": "skeleton.app.signed_offline_progress_preflight.v1",
        "status": "signed_progress_compatible_read_only_release_blocked",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "save_sha256": expected_save_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "signed_message_sha256": signed["signed_message_sha256"],
        "world_digest": plan["world_digest"],
        "replay_digest": plan["replay_digest"],
        "action_count": plan["action_count"],
        "source_archive_signature_verified": True,
        "save_world_binding_verified": True,
        "destination_reserved": False,
        "read_only": True,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
    }


def migrate_signed_offline_progress(
    archive: str | Path, destination: str | Path,
    original_save: str | Path, migrated_save: str | Path,
    public_key_file: str | Path, signature_file: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Admit signed original source, replay progress and independently reverify.

    Signature verification and replay compatibility precede any new output.
    The installer and publisher each use fresh no-clobber destinations. A
    failure after either publication requires manual quarantine, not deletion.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    before = _input_identities(
        archive, original_save, public_key_file, signature_file,
    )
    preflight = preflight_signed_offline_progress(
        archive, destination, original_save, migrated_save,
        public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    if before != _input_identities(
        archive, original_save, public_key_file, signature_file,
    ):
        raise SignedOfflineProgressMigrationError(
            "signed inputs changed after preflight"
        )

    migrated = migrate_offline_game_progress(
        archive, destination,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        original_save=original_save,
        expected_save_sha256=expected_save_sha256,
        migrated_save=migrated_save,
        authorized=True,
    )
    # Recheck the detached signature and every independently pinned input
    # after both outputs exist. Never accept a stale preflight as proof.
    signature_after = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    migrated_pin = migrated.get("independent_migrated_save_sha256")
    if type(migrated_pin) is not str:
        raise SignedOfflineProgressMigrationError("migration save pin absent")
    delivered = assure_signed_offline_delivery(
        destination, archive, migrated_save, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=migrated_pin,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    if (
        before != _input_identities(
            archive, original_save, public_key_file, signature_file,
        )
        or preflight.get("signed_message_sha256") != signature_after.get("signed_message_sha256")
        or delivered.get("source_archive_signature_verified") is not True
        or delivered.get("installed_source_archive_binding_verified") is not True
        or delivered.get("private_save_world_binding_verified") is not True
        or delivered.get("offline_gameplay_reexecuted") is not True
        or delivered.get("replay_digest") != migrated.get("replay_digest")
        or delivered.get("world_digest") != migrated.get("world_digest")
        or delivered.get("project_id") != migrated.get("project_id")
        or delivered.get("save_sha256") != migrated_pin
        or delivered.get("archive_sha256") != expected_archive_sha256
        or delivered.get("manifest_sha256") != expected_manifest_sha256
        or delivered.get("public_key_sha256") != expected_public_key_sha256
        or migrated.get("release_certified") is not False
        or delivered.get("release_certified") is not False
    ):
        raise SignedOfflineProgressMigrationError(
            "signed source, installed game and migrated progress disagree"
        )
    return {
        "schema": SCHEMA,
        "status": "signed_source_progress_migrated_replayed_release_blocked",
        "project_id": delivered["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "original_save_sha256": expected_save_sha256,
        "migrated_save_sha256": migrated_pin,
        "public_key_sha256": expected_public_key_sha256,
        "world_digest": delivered["world_digest"],
        "replay_digest": delivered["replay_digest"],
        "action_count": delivered["action_count"],
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "fresh_destination_no_clobber": True,
        "migration_atomic_across_destinations": False,
        "automatic_rollback_performed": False,
        "late_failure_requires_quarantine": True,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app migrate-signed-progress",
        description="Install signed original game and migrate a pinned private replay",
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--original-save", required=True)
    parser.add_argument("--migrated-save", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-save-sha256", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--preflight-only", action="store_true",
                        help="verify all inputs and destination admission without writing")
    args = parser.parse_args(argv)
    try:
        operation = (preflight_signed_offline_progress if args.preflight_only
                     else migrate_signed_offline_progress)
        result = operation(
            args.archive, args.destination, args.original_save,
            args.migrated_save, args.public_key, args.signature,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_save_sha256=args.expected_save_sha256,
            expected_public_key_sha256=args.expected_public_key_sha256,
            authorized=args.trusted_local_operator,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "SignedOfflineProgressMigrationError",
    "preflight_signed_offline_progress", "migrate_signed_offline_progress", "main",
]
