"""Fail-closed recovery of a quarantined offline install into a fresh directory.

The damaged source is never repaired, adopted, overwritten, deleted or cleared.
The independently pinned original ZIP is the only source for a new install.
A late failure leaves the new destination for operator quarantine as well.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import (
    _assert_original_root, _inventory, _root_fd,
)
from skeleton.app.offline_archive_install import (
    install_offline_game_source, preflight_offline_game_install,
)
from skeleton.app.offline_install_quarantine import (
    _file_identity, inspect_offline_install_quarantine,
)
from skeleton.app.offline_install_reconciliation import (
    _identity, reconcile_installed_game_archive,
)

SCHEMA = "skeleton.app.offline_install_fresh_recovery.v1"


class OfflineInstallRecoveryError(ValueError):
    """A quarantine, fresh destination or canonical replay failed admission."""


def _quarantine_identity(path: str | Path) -> tuple[object, ...]:
    """Bounded nofollow inventory with inode identities across recovery."""
    root = Path(path).expanduser().absolute()
    fd = _root_fd(root)
    try:
        _assert_original_root(root, fd)
        before = _identity(fd)
        names = _inventory(fd)
        observed = tuple((name, _file_identity(fd, name)) for name in sorted(names))
        _assert_original_root(root, fd)
        if _identity(fd) != before or _inventory(fd) != names:
            raise OfflineInstallRecoveryError(
                "quarantined source changed during identity inventory"
            )
        return before, observed
    finally:
        os.close(fd)


def recover_quarantined_offline_install(
    quarantined_source: str | Path,
    archive: str | Path,
    fresh_destination: str | Path,
    *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Inspect an abandoned partial install and rebuild from the pinned ZIP.

    No rollback is attempted: the first destination stays quarantined, and
    a failed new destination must also be inspected by its owner. A preflight
    is not a reservation; the installer independently repeats admission.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    partial = Path(quarantined_source).expanduser().absolute()
    target = Path(fresh_destination).expanduser().absolute()
    if partial == target or partial in target.parents or target in partial.parents:
        raise OfflineInstallRecoveryError(
            "fresh recovery requires disjoint installation directories"
        )
    identity = _quarantine_identity(partial)
    before = inspect_offline_install_quarantine(
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
    if (ready.get("destination_available_at_inspection") is not True
            or ready.get("destination_reserved") is not False
            or before.get("quarantine_cleared") is not False
            or before.get("release_certified") is not False):
        raise OfflineInstallRecoveryError(
            "quarantine or fresh destination failed read-only admission"
        )
    if (identity != _quarantine_identity(partial)
            or before != inspect_offline_install_quarantine(
                partial, archive,
                expected_archive_sha256=expected_archive_sha256,
                expected_manifest_sha256=expected_manifest_sha256,
                authorized=True,
            )):
        raise OfflineInstallRecoveryError(
            "quarantine changed before fresh installation"
        )

    installed = install_offline_game_source(
        archive, target,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    verified = reconcile_installed_game_archive(
        target, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    after = inspect_offline_install_quarantine(
        partial, archive,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (identity != _quarantine_identity(partial) or before != after
            or installed.get("source_installation_verified") is not True
            or verified.get("installed_source_archive_binding_verified") is not True
            or verified.get("offline_gameplay_reexecuted") is not True
            or installed.get("project_id") != verified.get("project_id")
            or installed.get("world_digest") != verified.get("world_digest")
            or installed.get("manifest_sha256") != expected_manifest_sha256
            or verified.get("archive_sha256") != expected_archive_sha256
            or verified.get("release_certified") is not False):
        raise OfflineInstallRecoveryError(
            "fresh installation or quarantined source changed during recovery"
        )
    return {
        "schema": SCHEMA,
        "status": "fresh_source_reinstalled_quarantine_retained_release_blocked",
        "project_id": verified["project_id"],
        "manifest_sha256": expected_manifest_sha256,
        "archive_sha256": expected_archive_sha256,
        "world_digest": verified["world_digest"],
        "installed_files": verified["matched_source_files"],
        "quarantined_missing_files": before["missing_files"],
        "quarantined_extra_files": before["extra_files"],
        "quarantined_mismatched_files": before["mismatched_files"],
        "fresh_source_installation_verified": True,
        "offline_gameplay_reexecuted": True,
        "original_quarantine_retained": True,
        "original_quarantine_cleared": False,
        "original_quarantine_mutated": False,
        "fresh_destination_no_clobber": True,
        "automatic_rollback_performed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app recover-install",
        description="Reinstall pinned source to a new directory; retain partial quarantine",
    )
    parser.add_argument("--quarantined", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = recover_quarantined_offline_install(
            args.quarantined, args.archive, args.destination,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
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


__all__ = ["SCHEMA", "OfflineInstallRecoveryError", "recover_quarantined_offline_install", "main"]
