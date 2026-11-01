"""Read-only, independently pinned installed-source versus delivery-archive replay.

An earlier installer success is not evidence that the installed game still
matches its original archive. This operation never writes to either source.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import hmac
import os
from pathlib import Path
import stat
from zipfile import ZipFile

from skeleton.ai.game_builder.dual_runtime_verify import (
    _MAX_BYTES, _MAX_FILES, _assert_original_root, _read, _root_fd,
    verify_exported_package,
)
from skeleton.app.offline_delivery_archive import (
    _parent as _archive_parent, _read_private_archive,
    inspect_offline_game_archive,
)

SCHEMA = "skeleton.app.offline_install_reconciliation.v1"


class OfflineInstallReconciliationError(ValueError):
    """Installed game source cannot be bound to its independently pinned ZIP."""


def _identity(fd: int) -> tuple[int, ...]:
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o022):
        raise OfflineInstallReconciliationError("installed root is not owner-controlled")
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid,
        info.st_mtime_ns, info.st_ctime_ns,
    )


def _archive_identity(path: str | Path) -> tuple[int, ...]:
    """Detect even same-byte archive inode substitution during reconciliation."""
    target, fd = _archive_parent(path)
    try:
        info = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o077):
            raise OfflineInstallReconciliationError("archive is not owner-private")
        _assert_original_root(target.parent, fd)
        return (
            info.st_dev, info.st_ino, info.st_size, info.st_mode,
            info.st_uid, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns,
        )
    finally:
        os.close(fd)


def reconcile_installed_game_archive(
    installed_source: str | Path, archive: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Compare all installed bytes to a canonical pinned ZIP and replay twice.

    The pins are externally supplied, never learned from untrusted files.
    This is a point-in-time proof, not a persistent filesystem lock or a
    consumer, rights, native-device, or signed-package qualification.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    original_archive = _archive_identity(archive)
    before_archive = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    root = Path(installed_source).expanduser().absolute()
    fd = _root_fd(root)
    try:
        original = _identity(fd)
        _assert_original_root(root, fd)
        before = verify_exported_package(
            root, expected_manifest_sha256=expected_manifest_sha256,
            authorized=True,
        )
        if (before.get("offline_gameplay_reexecuted") is not True
                or before.get("manifest_sha256") != expected_manifest_sha256
                or before.get("verified_files") != before_archive["archived_files"]
                or before.get("release_certified") is not False
                or before.get("godot_executed") is not False):
            raise OfflineInstallReconciliationError(
                "installed game failed canonical replay acceptance"
            )
        raw = _read_private_archive(archive)
        if not hmac.compare_digest(sha256(raw).hexdigest(), expected_archive_sha256):
            raise OfflineInstallReconciliationError("archive changed after inspection")
        matched = 0
        total = 0
        with ZipFile(BytesIO(raw), "r", allowZip64=False) as bundle:
            entries = bundle.infolist()
            if (len(entries) != before_archive["archived_files"]
                    or not 1 <= len(entries) <= _MAX_FILES + 1):
                raise OfflineInstallReconciliationError("archive inventory changed")
            for entry in entries:
                total += entry.file_size
                if entry.file_size < 0 or total > _MAX_BYTES:
                    raise OfflineInstallReconciliationError("source byte budget exceeded")
                archived = bundle.read(entry)
                installed = _read(fd, entry.filename, entry.file_size,
                                  owner_controlled=True)
                if not hmac.compare_digest(
                    sha256(archived).digest(), sha256(installed).digest()
                ):
                    raise OfflineInstallReconciliationError(
                        "installed file differs from pinned archive"
                    )
                matched += 1
        _assert_original_root(root, fd)
        if _identity(fd) != original:
            raise OfflineInstallReconciliationError("installed root changed")
        after = verify_exported_package(
            root, expected_manifest_sha256=expected_manifest_sha256,
            authorized=True,
        )
        after_archive = inspect_offline_game_archive(
            archive, expected_archive_sha256=expected_archive_sha256,
            expected_manifest_sha256=expected_manifest_sha256, authorized=True,
        )
        _assert_original_root(root, fd)
        if (_identity(fd) != original or before != after
                or _archive_identity(archive) != original_archive
                or before_archive != after_archive
                or matched != after["verified_files"]):
            raise OfflineInstallReconciliationError(
                "source or archive changed during reconciliation"
            )
        return {
            "schema": SCHEMA,
            "status": "installed_source_archive_reconciled_release_blocked",
            "project_id": after["project_id"],
            "manifest_sha256": expected_manifest_sha256,
            "archive_sha256": expected_archive_sha256,
            "world_digest": after["world_digest"],
            "replay_digest": after["replay_digest"],
            "matched_source_files": matched,
            "offline_gameplay_reexecuted": True,
            "installed_source_archive_binding_verified": True,
            "read_only": True,
            "source_mutated": False,
            "model_inference_observed": False,
            "native_godot_executed": False,
            "native_device_qualified": False,
            "rights_certified": False,
            "package_signed": False,
            "release_certified": False,
        }
    finally:
        os.close(fd)


__all__ = ["SCHEMA", "OfflineInstallReconciliationError",
           "reconcile_installed_game_archive"]
