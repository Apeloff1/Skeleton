"""Recover damaged original-game source and private progress from signed custody.

The damaged installation is never used as an input to the new playable game.
A separately pinned original ZIP and save are replayed and installed into fresh
no-clobber destinations. No multi-path atomicity or native release is claimed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import _pin
from skeleton.app.offline_install_quarantine import inspect_offline_install_quarantine
from skeleton.app.offline_install_recovery import _quarantine_identity
from skeleton.app.offline_signed_progress_migration import (
    _input_identities, preflight_signed_offline_progress,
    migrate_signed_offline_progress,
)
from skeleton.app.offline_signed_delivery import assure_signed_offline_delivery

SCHEMA = "skeleton.app.signed_quarantine_progress_recovery.v1"


class SignedQuarantineProgressRecoveryError(ValueError):
    """Quarantined source, signature, save, or installed replay disagreed."""


def _separate_paths(
    quarantined: str | Path, destination: str | Path, migrated_save: str | Path,
) -> Path:
    partial = Path(quarantined).expanduser().absolute()
    fresh = Path(destination).expanduser().absolute()
    new_save = Path(migrated_save).expanduser().absolute()
    if (
        partial == fresh or partial in fresh.parents or fresh in partial.parents
        or new_save == partial or partial in new_save.parents
        or new_save == fresh or fresh in new_save.parents
    ):
        raise SignedQuarantineProgressRecoveryError(
            "new installation and migrated save must be disjoint from quarantine"
        )
    return partial


def preflight_signed_quarantine_progress(
    quarantined_source: str | Path,
    archive: str | Path,
    fresh_destination: str | Path,
    original_save: str | Path,
    migrated_save: str | Path,
    public_key_file: str | Path,
    signature_file: str | Path,
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Read-only signed quarantine, replay and dual-destination preflight.

    This checks both independent inputs and destination availability without
    publishing a source tree or save. It is not a reservation or release grant.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, pin in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("save", expected_save_sha256),
        ("public key", expected_public_key_sha256),
    ):
        _pin(pin, name)
    partial = _separate_paths(quarantined_source, fresh_destination, migrated_save)
    original_quarantine = _quarantine_identity(partial)
    original_inputs = _input_identities(
        archive, original_save, public_key_file, signature_file,
    )
    quarantine = inspect_offline_install_quarantine(
        partial, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    ready = preflight_signed_offline_progress(
        archive, fresh_destination, original_save, migrated_save,
        public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    if (
        original_quarantine != _quarantine_identity(partial)
        or original_inputs != _input_identities(
            archive, original_save, public_key_file, signature_file,
        )
        or quarantine.get("quarantine_cleared") is not False
        or ready.get("source_archive_signature_verified") is not True
        or ready.get("save_world_binding_verified") is not True
        or ready.get("destination_reserved") is not False
        or ready.get("release_certified") is not False
    ):
        raise SignedQuarantineProgressRecoveryError(
            "signed quarantine progress preflight unqualified"
        )
    return {
        "schema": "skeleton.app.signed_quarantine_progress_preflight.v1",
        "status": "signed_quarantine_progress_ready_unreserved_release_blocked",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "original_save_sha256": expected_save_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "world_digest": ready["world_digest"],
        "replay_digest": ready["replay_digest"],
        "action_count": ready["action_count"],
        "quarantined_missing_files": quarantine["missing_files"],
        "quarantined_extra_files": quarantine["extra_files"],
        "quarantined_mismatched_files": quarantine["mismatched_files"],
        "source_archive_signature_verified": True,
        "private_save_world_binding_verified": True,
        "original_quarantine_retained": True,
        "original_quarantine_cleared": False,
        "destination_reserved": False,
        "migrated_save_published": False,
        "read_only": True,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
    }


def recover_signed_quarantine_progress(
    quarantined_source: str | Path,
    archive: str | Path,
    fresh_destination: str | Path,
    original_save: str | Path,
    migrated_save: str | Path,
    public_key_file: str | Path,
    signature_file: str | Path,
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Bind an untouched quarantine to a fresh signed game and replayed save.

    Every output is independently verified. A failure after installation or
    save publication leaves those outputs for operator quarantine; neither
    damaged source nor owner progress is deleted or silently repaired.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, pin in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("save", expected_save_sha256),
        ("public key", expected_public_key_sha256),
    ):
        _pin(pin, name)
    partial = _separate_paths(quarantined_source, fresh_destination, migrated_save)
    original_quarantine = _quarantine_identity(partial)
    original_inputs = _input_identities(
        archive, original_save, public_key_file, signature_file,
    )
    quarantine_before = inspect_offline_install_quarantine(
        partial, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    admission = preflight_signed_offline_progress(
        archive, fresh_destination, original_save, migrated_save,
        public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    if (
        quarantine_before.get("quarantine_cleared") is not False
        or quarantine_before.get("release_certified") is not False
        or admission.get("source_archive_signature_verified") is not True
        or admission.get("save_world_binding_verified") is not True
        or admission.get("destination_reserved") is not False
        or admission.get("release_certified") is not False
        or original_quarantine != _quarantine_identity(partial)
        or original_inputs != _input_identities(
            archive, original_save, public_key_file, signature_file,
        )
    ):
        raise SignedQuarantineProgressRecoveryError(
            "quarantine or signed progress changed before publication"
        )

    migrated = migrate_signed_offline_progress(
        archive, fresh_destination, original_save, migrated_save,
        public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    new_pin = migrated.get("migrated_save_sha256")
    if type(new_pin) is not str:
        raise SignedQuarantineProgressRecoveryError("migrated save pin missing")
    delivered = assure_signed_offline_delivery(
        fresh_destination, archive, migrated_save, public_key_file,
        signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=new_pin,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    quarantine_after = inspect_offline_install_quarantine(
        partial, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (
        original_quarantine != _quarantine_identity(partial)
        or quarantine_before != quarantine_after
        or original_inputs != _input_identities(
            archive, original_save, public_key_file, signature_file,
        )
        or delivered.get("source_archive_signature_verified") is not True
        or delivered.get("installed_source_archive_binding_verified") is not True
        or delivered.get("private_save_world_binding_verified") is not True
        or delivered.get("offline_gameplay_reexecuted") is not True
        or delivered.get("world_digest") != migrated.get("world_digest")
        or delivered.get("replay_digest") != migrated.get("replay_digest")
        or delivered.get("project_id") != migrated.get("project_id")
        or delivered.get("save_sha256") != new_pin
        or migrated.get("original_save_sha256") != expected_save_sha256
        or migrated.get("release_certified") is not False
        or delivered.get("release_certified") is not False
    ):
        raise SignedQuarantineProgressRecoveryError(
            "signed source, original quarantine or migrated replay changed"
        )
    return {
        "schema": SCHEMA,
        "status": "signed_game_and_progress_recovered_quarantine_retained_release_blocked",
        "project_id": delivered["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "original_save_sha256": expected_save_sha256,
        "migrated_save_sha256": new_pin,
        "public_key_sha256": expected_public_key_sha256,
        "world_digest": delivered["world_digest"],
        "replay_digest": delivered["replay_digest"],
        "action_count": delivered["action_count"],
        "quarantined_missing_files": quarantine_after["missing_files"],
        "quarantined_extra_files": quarantine_after["extra_files"],
        "quarantined_mismatched_files": quarantine_after["mismatched_files"],
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "original_quarantine_retained": True,
        "original_quarantine_cleared": False,
        "original_quarantine_mutated": False,
        "fresh_destination_no_clobber": True,
        "migration_atomic_across_destinations": False,
        "late_failure_requires_quarantine": True,
        "automatic_rollback_performed": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "publisher_identity_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app recover-signed-progress",
        description="Recover a damaged game and private replay into fresh paths",
    )
    parser.add_argument("--quarantined", required=True)
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
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        operation = (preflight_signed_quarantine_progress if args.preflight_only
                     else recover_signed_quarantine_progress)
        receipt = operation(
            args.quarantined, args.archive, args.destination,
            args.original_save, args.migrated_save, args.public_key,
            args.signature,
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
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "SignedQuarantineProgressRecoveryError",
    "preflight_signed_quarantine_progress",
    "recover_signed_quarantine_progress", "main",
]
