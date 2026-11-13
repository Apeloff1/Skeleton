"""Install a cryptographically verified original source ZIP without clobbering.

Signature verification occurs before any destination reservation, and is
repeated after installation. Late failures retain the new directory for
operator quarantine; no unsafe rollback or consumer release is implied.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from skeleton.app.offline_archive_signature import (
    _pin, _read_detached_file, source_archive_signature_message,
    verify_offline_source_archive_signature,
)
from skeleton.app.offline_archive_install import (
    install_offline_game_source, preflight_offline_game_install,
)
from skeleton.app.offline_install_reconciliation import reconcile_installed_game_archive
from skeleton.app.offline_progress_compatibility import _archive_identity

SCHEMA = "skeleton.app.signed_offline_source_install.v1"


class SignedOfflineSourceInstallError(ValueError):
    """Signature, fresh destination or installed original source failed."""


def _signature_identities(
    archive: str | Path, key: str | Path, signature: str | Path,
) -> tuple[object, ...]:
    return (
        _archive_identity(archive),
        _read_detached_file(key, length=32)[1],
        _read_detached_file(signature, length=64)[1],
    )


def install_signed_offline_game_source(
    archive: str | Path, destination: str | Path,
    public_key_file: str | Path, signature_file: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Verify detached signature before mkdir, install, then reverify."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    source_archive_signature_message(
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    _pin(expected_public_key_sha256, "public key")
    identities = _signature_identities(archive, public_key_file, signature_file)
    signed_before = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    preflight = preflight_offline_game_install(
        archive, destination,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (preflight.get("destination_reserved") is not False
            or preflight.get("destination_available_at_inspection") is not True
            or identities != _signature_identities(
                archive, public_key_file, signature_file,
            )):
        raise SignedOfflineSourceInstallError(
            "signed source changed before installation reservation"
        )
    # Canonical installer atomically reserves a new directory. Never retry by
    # overwriting it; any failure after reservation needs explicit quarantine.
    installed = install_offline_game_source(
        archive, destination,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    reconciled = reconcile_installed_game_archive(
        destination, archive,
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
    if (identities != _signature_identities(
            archive, public_key_file, signature_file,
        ) or signed_before != signed_after
            or signed_after.get("source_archive_signature_verified") is not True
            or installed.get("source_installation_verified") is not True
            or reconciled.get("installed_source_archive_binding_verified") is not True
            or reconciled.get("offline_gameplay_reexecuted") is not True
            or installed.get("world_digest") != reconciled.get("world_digest")
            or installed.get("project_id") != reconciled.get("project_id")
            or installed.get("manifest_sha256") != expected_manifest_sha256
            or reconciled.get("archive_sha256") != expected_archive_sha256
            or reconciled.get("release_certified") is not False):
        raise SignedOfflineSourceInstallError(
            "signed archive or installed game failed post-install reconciliation"
        )
    return {
        "schema": SCHEMA,
        "status": "signed_original_source_installed_playable_release_blocked",
        "project_id": installed["project_id"],
        "manifest_sha256": expected_manifest_sha256,
        "archive_sha256": expected_archive_sha256,
        "public_key_sha256": expected_public_key_sha256,
        "world_digest": reconciled["world_digest"],
        "installed_files": reconciled["matched_source_files"],
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "fresh_destination_no_clobber": True,
        "late_failure_requires_quarantine": True,
        "automatic_rollback_performed": False,
        "private_signing_key_loaded": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "publisher_identity_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app install-signed-source",
        description="Install a detached-signed original game ZIP into a fresh directory",
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = install_signed_offline_game_source(
            args.archive, args.destination, args.public_key, args.signature,
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
    "SCHEMA", "SignedOfflineSourceInstallError",
    "install_signed_offline_game_source", "main",
]
