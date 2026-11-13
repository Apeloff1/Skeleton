"""Recover a quarantined offline game only from independently pinned signed source.

No quarantine is adopted, repaired, deleted or silently released. The archive,
public key and signature are verified before reserving a fresh destination and
again after canonical installation/replay. A late failure leaves the new
destination for explicit quarantine rather than attempting unsafe rollback.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import (
    _pin, _read_detached_file, verify_offline_source_archive_signature,
)
from skeleton.app.offline_archive_install import preflight_offline_game_install
from skeleton.app.offline_install_quarantine import inspect_offline_install_quarantine
from skeleton.app.offline_install_recovery import (
    _quarantine_identity, recover_quarantined_offline_install,
)
from skeleton.app.offline_install_reconciliation import reconcile_installed_game_archive
from skeleton.app.offline_progress_compatibility import _archive_identity

SCHEMA = "skeleton.app.signed_offline_install_recovery.v1"


class SignedOfflineInstallRecoveryError(ValueError):
    """Signed custody, quarantine, no-clobber or fresh replay was not proven."""


def _custody(
    quarantined: str | Path, archive: str | Path,
    public_key: str | Path, signature: str | Path,
) -> tuple[object, ...]:
    """Pin both content-bearing paths and the quarantined tree's inode inventory."""
    return (
        _quarantine_identity(quarantined),
        _archive_identity(archive),
        _read_detached_file(public_key, length=32)[1],
        _read_detached_file(signature, length=64)[1],
    )


def preflight_signed_offline_install_recovery(
    quarantined_source: str | Path,
    archive: str | Path,
    fresh_destination: str | Path,
    public_key_file: str | Path,
    signature_file: str | Path,
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Read-only signature, quarantine and fresh destination admission.

    The result is an observation, not a lease. Publication must repeat all
    checks and independently reserve a destination with O_EXCL/mkdir.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, pin in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("public key", expected_public_key_sha256),
    ):
        _pin(pin, name)
    partial = Path(quarantined_source).expanduser().absolute()
    target = Path(fresh_destination).expanduser().absolute()
    if partial == target or partial in target.parents or target in partial.parents:
        raise SignedOfflineInstallRecoveryError(
            "quarantined and fresh installation paths must be disjoint"
        )
    original = _custody(partial, archive, public_key_file, signature_file)
    signed = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    quarantined = inspect_offline_install_quarantine(
        partial, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    ready = preflight_offline_game_install(
        archive, target,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (
        original != _custody(partial, archive, public_key_file, signature_file)
        or signed.get("source_archive_signature_verified") is not True
        or signed.get("release_certified") is not False
        or quarantined.get("quarantine_cleared") is not False
        or ready.get("destination_available_at_inspection") is not True
        or ready.get("destination_reserved") is not False
        or ready.get("release_certified") is not False
    ):
        raise SignedOfflineInstallRecoveryError("signed recovery preflight unqualified")
    return {
        "schema": "skeleton.app.signed_offline_install_recovery_preflight.v1",
        "status": "signed_quarantine_recovery_ready_unreserved_release_blocked",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "signed_message_sha256": signed["signed_message_sha256"],
        "quarantined_missing_files": quarantined["missing_files"],
        "quarantined_extra_files": quarantined["extra_files"],
        "quarantined_mismatched_files": quarantined["mismatched_files"],
        "source_archive_signature_verified": True,
        "original_quarantine_retained": True,
        "original_quarantine_cleared": False,
        "destination_reserved": False,
        "source_installation_verified": False,
        "offline_gameplay_reexecuted": False,
        "read_only": True,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
    }


def recover_signed_offline_game_install(
    quarantined_source: str | Path,
    archive: str | Path,
    fresh_destination: str | Path,
    public_key_file: str | Path,
    signature_file: str | Path,
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Rebuild a damaged install from signed original bytes, never from quarantine.

    The independently supplied pins are admission inputs, not inferred trust.
    The fresh destination is reserved only by the canonical no-clobber installer.
    This operation is not a native package signature, device or rights approval.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    for name, pin in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("public key", expected_public_key_sha256),
    ):
        _pin(pin, name)
    partial = Path(quarantined_source).expanduser().absolute()
    target = Path(fresh_destination).expanduser().absolute()
    if partial == target or partial in target.parents or target in partial.parents:
        raise SignedOfflineInstallRecoveryError(
            "quarantined and fresh installation paths must be disjoint"
        )

    original = _custody(partial, archive, public_key_file, signature_file)
    signed_before = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    quarantined_before = inspect_offline_install_quarantine(
        partial, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    ready = preflight_offline_game_install(
        archive, target,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (
        signed_before.get("source_archive_signature_verified") is not True
        or signed_before.get("release_certified") is not False
        or quarantined_before.get("quarantine_cleared") is not False
        or ready.get("destination_available_at_inspection") is not True
        or ready.get("destination_reserved") is not False
        or original != _custody(partial, archive, public_key_file, signature_file)
    ):
        raise SignedOfflineInstallRecoveryError(
            "signed recovery admission changed before fresh reservation"
        )

    recovered = recover_quarantined_offline_install(
        partial, archive, target,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    # These post-install checks are independent of the recovery receipt.
    reconciled = reconcile_installed_game_archive(
        target, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    signed_after = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    quarantined_after = inspect_offline_install_quarantine(
        partial, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (
        original != _custody(partial, archive, public_key_file, signature_file)
        or signed_before != signed_after
        or quarantined_before != quarantined_after
        or recovered.get("fresh_source_installation_verified") is not True
        or recovered.get("original_quarantine_retained") is not True
        or recovered.get("original_quarantine_cleared") is not False
        or recovered.get("automatic_rollback_performed") is not False
        or reconciled.get("installed_source_archive_binding_verified") is not True
        or reconciled.get("offline_gameplay_reexecuted") is not True
        or recovered.get("project_id") != reconciled.get("project_id")
        or recovered.get("world_digest") != reconciled.get("world_digest")
        or recovered.get("manifest_sha256") != expected_manifest_sha256
        or reconciled.get("archive_sha256") != expected_archive_sha256
        or recovered.get("release_certified") is not False
        or reconciled.get("release_certified") is not False
    ):
        raise SignedOfflineInstallRecoveryError(
            "signed source, quarantine or installed playable game changed"
        )
    return {
        "schema": SCHEMA,
        "status": "signed_fresh_source_recovered_quarantine_retained_release_blocked",
        "project_id": reconciled["project_id"],
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "signed_message_sha256": signed_after["signed_message_sha256"],
        "world_digest": reconciled["world_digest"],
        "replay_digest": reconciled["replay_digest"],
        "installed_files": reconciled["matched_source_files"],
        "quarantined_missing_files": quarantined_after["missing_files"],
        "quarantined_extra_files": quarantined_after["extra_files"],
        "quarantined_mismatched_files": quarantined_after["mismatched_files"],
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "original_quarantine_retained": True,
        "original_quarantine_cleared": False,
        "original_quarantine_mutated": False,
        "fresh_destination_no_clobber": True,
        "late_failure_requires_quarantine": True,
        "automatic_rollback_performed": False,
        "private_signing_key_loaded": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app recover-signed-install",
        description="Rebuild quarantined source from a pinned detached-signed ZIP",
    )
    parser.add_argument("--quarantined", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        operation = (preflight_signed_offline_install_recovery if args.preflight_only
                     else recover_signed_offline_game_install)
        receipt = operation(
            args.quarantined, args.archive, args.destination,
            args.public_key, args.signature,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
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
    "SCHEMA", "SignedOfflineInstallRecoveryError",
    "preflight_signed_offline_install_recovery",
    "recover_signed_offline_game_install", "main",
]
