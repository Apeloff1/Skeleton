"""Read-only cross-custody acceptance for a delivered original offline game.

A successful result proves only a point-in-time Python replay and the binding
of an installed source tree, original ZIP and owner-private save to independently
supplied SHA-256 pins. It never signs packages or certifies rights or devices.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import _assert_original_root, _root_fd
from skeleton.app.offline_install_reconciliation import (
    _identity as _installed_identity,
    reconcile_installed_game_archive,
)
from skeleton.app.offline_progress_compatibility import (
    _archive_identity,
    verify_archived_progress_binding,
)
from skeleton.app.offline_progress_recovery import reconcile_migrated_offline_progress
from skeleton.app.private_game_save import _parent as _save_parent, read_private_game_save

SCHEMA = "skeleton.app.offline_delivery_assurance.v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class OfflineDeliveryAssuranceError(ValueError):
    """A custody, replay, identity or cross-component contract failed."""


def _pin(value: str, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise OfflineDeliveryAssuranceError(
            "independent " + name + " SHA-256 pin required"
        )
    return value


def _source_identity(path: str | Path) -> tuple[int, ...]:
    root = Path(path).expanduser().absolute()
    fd = _root_fd(root)
    try:
        _assert_original_root(root, fd)
        return _installed_identity(fd)
    finally:
        os.close(fd)


def _save_identity(path: str | Path) -> tuple[int, ...]:
    target, parent_fd = _save_parent(path)
    try:
        info = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise OfflineDeliveryAssuranceError("save inode is not owner-private")
        _assert_original_root(target.parent, parent_fd)
        return (
            info.st_dev, info.st_ino, info.st_size, info.st_nlink,
            info.st_uid, info.st_mode, info.st_mtime_ns, info.st_ctime_ns,
        )
    finally:
        os.close(parent_fd)


def assure_offline_delivery(
    installed_source: str | Path,
    archive: str | Path,
    private_save: str | Path,
    *,
    expected_manifest_sha256: str,
    expected_archive_sha256: str,
    expected_save_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Independently recheck installation, ZIP, and replay before a handoff.

    This is an observational assurance barrier, not a transaction lock. All
    inputs remain immutable by this function; a later writer can still change
    them. Every component is reverified after the cross-component replay.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    manifest_pin = _pin(expected_manifest_sha256, "manifest")
    archive_pin = _pin(expected_archive_sha256, "archive")
    save_pin = _pin(expected_save_sha256, "save")

    source_before = _source_identity(installed_source)
    archive_before = _archive_identity(archive)
    save_before = _save_identity(private_save)

    installed = reconcile_installed_game_archive(
        installed_source, archive,
        expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin, authorized=True,
    )
    raw = read_private_game_save(
        private_save, expected_sha256=save_pin, authorized=True,
    )
    archived = verify_archived_progress_binding(
        archive, raw, expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin,
        expected_save_sha256=save_pin, authorized=True,
    )
    recovered = reconcile_migrated_offline_progress(
        installed_source, private_save,
        expected_manifest_sha256=manifest_pin,
        expected_save_sha256=save_pin,
        archive=archive, expected_archive_sha256=archive_pin,
        authorized=True,
    )

    # Reverify each custody plane after the other planes have been read. A
    # same-byte inode swap is not accepted merely because the hash matches.
    installed_again = reconcile_installed_game_archive(
        installed_source, archive,
        expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin, authorized=True,
    )
    raw_again = read_private_game_save(
        private_save, expected_sha256=save_pin, authorized=True,
    )
    archived_again = verify_archived_progress_binding(
        archive, raw_again, expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin,
        expected_save_sha256=save_pin, authorized=True,
    )
    if (source_before != _source_identity(installed_source)
            or archive_before != _archive_identity(archive)
            or save_before != _save_identity(private_save)
            or installed != installed_again or archived != archived_again
            or not hmac.compare_digest(raw, raw_again)):
        raise OfflineDeliveryAssuranceError(
            "delivery custody changed during independent replay"
        )

    if (installed.get("installed_source_archive_binding_verified") is not True
            or installed.get("offline_gameplay_reexecuted") is not True
            or archived.get("save_world_binding_verified") is not True
            or archived.get("private_save_replayed") is not True
            or recovered.get("installed_source_replayed") is not True
            or recovered.get("private_save_replayed") is not True
            or recovered.get("original_archive_integrity_verified") is not True
            or any(receipt.get("release_certified") is not False
                   for receipt in (installed, archived, recovered))
            or len({installed.get("project_id"), archived.get("project_id"),
                    recovered.get("project_id")}) != 1
            or len({installed.get("world_digest"), archived.get("world_digest"),
                    recovered.get("world_digest")}) != 1
            or not hmac.compare_digest(
                str(archived.get("replay_digest")),
                str(recovered.get("replay_digest")),
            )
            or archived.get("action_count") != recovered.get("action_count")
            or installed.get("manifest_sha256") != manifest_pin
            or installed.get("archive_sha256") != archive_pin
            or archived.get("save_sha256") != save_pin
            or recovered.get("save_sha256") != save_pin):
        raise OfflineDeliveryAssuranceError(
            "installed source, archived world and saved replay disagree"
        )
    return {
        "schema": SCHEMA,
        "status": "offline_delivery_cross_custody_verified_release_blocked",
        "project_id": installed["project_id"],
        "manifest_sha256": manifest_pin,
        "archive_sha256": archive_pin,
        "save_sha256": save_pin,
        "world_digest": installed["world_digest"],
        "replay_digest": recovered["replay_digest"],
        "action_count": recovered["action_count"],
        "installed_files": installed["matched_source_files"],
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "read_only": True,
        "destination_reserved": False,
        "source_mutated": False,
        "migration_atomicity_proven": False,
        "model_inference_observed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app delivery-assurance",
        description="Read-only triple-pinned installed game / archive / save replay",
    )
    parser.add_argument("--installed", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--save", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-save-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = assure_offline_delivery(
            args.installed, args.archive, args.save,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_save_sha256=args.expected_save_sha256,
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


__all__ = ["SCHEMA", "OfflineDeliveryAssuranceError", "assure_offline_delivery", "main"]
