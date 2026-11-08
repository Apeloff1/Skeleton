"""Read-only inspection of quarantined partial offline source installations.

This diagnostic does not delete, overwrite, repair, adopt, or certify a
possibly partial destination. Every observed path is descriptor-relative
and bounded. Unexpected filesystem object types fail closed.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import hmac
import os
from pathlib import Path
from zipfile import ZipFile

from skeleton.ai.game_builder.dual_runtime_verify import (
    _MAX_BYTES, _assert_original_root, _child_fd, _inventory, _parts,
    _read, _root_fd,
    verify_exported_package,
)
from skeleton.app.offline_delivery_archive import (
    _read_private_archive, inspect_offline_game_archive,
)
from skeleton.app.offline_install_reconciliation import (
    _archive_identity, _identity,
)

SCHEMA = "skeleton.app.offline_install_quarantine_inspection.v1"


class OfflineInstallQuarantineError(ValueError):
    """A quarantined installation cannot be safely inspected."""

def _file_identity(fd: int, name: str) -> tuple[int, ...]:
    """Reopen a canonical child without following a replaced path or symlink."""
    child = _child_fd(fd, _parts(name), directory=False)
    try:
        info = os.fstat(child)
        return (
            info.st_dev, info.st_ino, info.st_size, info.st_mode,
            info.st_nlink, info.st_uid, info.st_mtime_ns, info.st_ctime_ns,
        )
    finally:
        os.close(child)


def inspect_offline_install_quarantine(
    source_directory: str | Path, archive: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Classify missing, extra and corrupted files without changing custody.

    A complete matching inventory may be replay-verified, but still requires
    the normal installation, exact-head CI, rights and device release gates.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    archive_before_id = _archive_identity(archive)
    archive_before = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    root = Path(source_directory).expanduser().absolute()
    fd = _root_fd(root)
    try:
        root_before = _identity(fd)
        _assert_original_root(root, fd)
        observed = _inventory(fd)
        raw = _read_private_archive(archive)
        if not hmac.compare_digest(sha256(raw).hexdigest(), expected_archive_sha256):
            raise OfflineInstallQuarantineError("archive changed after inspection")
        total = 0
        mismatched = 0
        fingerprints: dict[str, tuple[bytes, tuple[int, ...], int]] = {}
        with ZipFile(BytesIO(raw), "r", allowZip64=False) as bundle:
            expected = {entry.filename: entry for entry in bundle.infolist()}
            if len(expected) != archive_before["archived_files"]:
                raise OfflineInstallQuarantineError("archive inventory changed")
            for name in sorted(observed & set(expected)):
                entry = expected[name]
                total += entry.file_size
                if entry.file_size < 0 or total > _MAX_BYTES:
                    raise OfflineInstallQuarantineError("inspection byte budget exceeded")
                current = _read(fd, name, entry.file_size, owner_controlled=True)
                digest = sha256(current).digest()
                fingerprints[name] = (digest, _file_identity(fd, name), entry.file_size)
                if not hmac.compare_digest(digest, sha256(bundle.read(entry)).digest()):
                    mismatched += 1
        missing = len(set(expected) - observed)
        extra = len(observed - set(expected))
        _assert_original_root(root, fd)
        if _identity(fd) != root_before:
            raise OfflineInstallQuarantineError("quarantine root changed during inspection")
        replay = None
        if missing == extra == mismatched == 0:
            replay = verify_exported_package(
                root, expected_manifest_sha256=expected_manifest_sha256,
                authorized=True,
            )
            if (replay.get("offline_gameplay_reexecuted") is not True
                    or replay.get("verified_files") != len(expected)
                    or replay.get("release_certified") is not False):
                raise OfflineInstallQuarantineError(
                    "complete source did not replay successfully"
                )
        archive_after = inspect_offline_game_archive(
            archive, expected_archive_sha256=expected_archive_sha256,
            expected_manifest_sha256=expected_manifest_sha256, authorized=True,
        )
        for name, (digest, identity, limit) in fingerprints.items():
            if (_file_identity(fd, name) != identity or not hmac.compare_digest(
                sha256(_read(fd, name, limit, owner_controlled=True)).digest(), digest
            )):
                raise OfflineInstallQuarantineError(
                    "quarantined source changed during inspection"
                )
        _assert_original_root(root, fd)
        if (_identity(fd) != root_before
                or _archive_identity(archive) != archive_before_id
                or archive_before != archive_after
                or _inventory(fd) != observed):
            raise OfflineInstallQuarantineError(
                "quarantined installation or archive changed during inspection"
            )
        return {
            "schema": SCHEMA,
            "status": "quarantine_inspected_release_blocked",
            "archive_sha256": expected_archive_sha256,
            "manifest_sha256": expected_manifest_sha256,
            "observed_source_files": len(observed),
            "expected_source_files": len(expected),
            "missing_files": missing,
            "extra_files": extra,
            "mismatched_files": mismatched,
            "complete_inventory_matches_archive": missing == extra == mismatched == 0,
            "offline_gameplay_reexecuted": replay is not None,
            "read_only": True,
            "source_mutated": False,
            "quarantine_cleared": False,
            "installation_approved": False,
            "native_device_qualified": False,
            "rights_certified": False,
            "package_signed": False,
            "release_certified": False,
        }
    finally:
        os.close(fd)


__all__ = [
    "SCHEMA", "OfflineInstallQuarantineError",
    "inspect_offline_install_quarantine",
]
