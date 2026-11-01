"""Install a pinned original game source ZIP into a new private local directory.

Installation is fail-closed and no-clobber. A partially populated directory
is deliberately left for operator quarantine on failure; it never receives a
success receipt. No archive member is executed, and this is not a signed
consumer installer or native hardware qualification.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import hmac
import os
from pathlib import Path
import re
import stat
from zipfile import ZipFile

from skeleton.ai.game_builder.dual_runtime_verify import (
    _assert_original_root, _parts, _root_fd, verify_exported_package,
)
from skeleton.app.offline_delivery_archive import (
    _read_private_archive, inspect_offline_game_archive,
)

SCHEMA = "skeleton.app.offline_source_install.v1"
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")


class OfflineSourceInstallError(ValueError):
    """A source installation failed integrity, ownership or no-clobber custody."""


def _parent(destination: str | Path) -> tuple[Path, int]:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise OfflineSourceInstallError("descriptor-safe source installation unavailable")
    target = Path(destination).expanduser().absolute()
    if not _NAME.fullmatch(target.name) or target.name in (".", ".."):
        raise OfflineSourceInstallError("invalid bounded source installation name")
    fd = _root_fd(target.parent)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022):
            raise OfflineSourceInstallError("installation parent must be owner-controlled")
        _assert_original_root(target.parent, fd)
    except BaseException:
        os.close(fd)
        raise
    return target, fd


def _directory(fd: int, part: str, *, known: tuple[int, int] | None) -> tuple[int, tuple[int, int]]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if known is None:
        os.mkdir(part, mode=0o700, dir_fd=fd)
        os.fsync(fd)
    opened = os.open(part, flags, dir_fd=fd)
    try:
        info = os.fstat(opened)
        identity = (info.st_dev, info.st_ino)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or
                (known is not None and identity != known)):
            raise OfflineSourceInstallError("installation directory identity changed")
        return opened, identity
    except BaseException:
        os.close(opened)
        raise


def _write_file(
    root_fd: int, path: str, payload: bytes,
    directories: dict[str, tuple[int, int]],
) -> None:
    parts = _parts(path)
    current = os.dup(root_fd)
    try:
        for depth, part in enumerate(parts[:-1], start=1):
            prefix = "/".join(parts[:depth])
            opened, identity = _directory(
                current, part, known=directories.get(prefix),
            )
            if prefix not in directories:
                directories[prefix] = identity
            os.close(current)
            current = opened
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        handle = os.open(parts[-1], flags, 0o600, dir_fd=current)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or before.st_nlink != 1 or before.st_mode & 0o077):
                raise OfflineSourceInstallError("installed source file is not private")
            offset = 0
            while offset < len(payload):
                written = os.write(handle, payload[offset:])
                if written <= 0:
                    raise OfflineSourceInstallError("source installation write stalled")
                offset += written
            os.fsync(handle)
            after = os.fstat(handle)
            if ((after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
                    or after.st_size != len(payload)):
                raise OfflineSourceInstallError("installed source file identity changed")
        finally:
            os.close(handle)
        os.fsync(current)
    finally:
        os.close(current)


def install_offline_game_source(
    archive: str | Path, destination: str | Path, *,
    expected_archive_sha256: str, expected_manifest_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Inspect two independently pinned digests, then install and replay-verify.

    A new destination directory is reserved atomically by mkdir, never
    replaced. All descendants are created with O_EXCL/O_NOFOLLOW and checked
    against descriptor identities. On any failure after reservation the
    directory remains unqualified for explicit operator quarantine.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    inspected = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    raw = _read_private_archive(archive)
    if not hmac.compare_digest(sha256(raw).hexdigest(), expected_archive_sha256):
        raise OfflineSourceInstallError("archive changed after inspection")
    target, parent_fd = _parent(destination)
    root_fd = None
    try:
        # Atomic no-clobber reservation. Never rename over an existing owner
        # directory, including an empty directory created by another writer.
        os.mkdir(target.name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
        root_fd, _identity = _directory(
            parent_fd, target.name,
            known=_stat_identity(parent_fd, target.name),
        )
        _assert_original_root(target, root_fd)
        directories: dict[str, tuple[int, int]] = {}
        with ZipFile(BytesIO(raw), "r", allowZip64=False) as bundle:
            for info in bundle.infolist():
                _write_file(root_fd, info.filename, bundle.read(info), directories)
        os.fsync(root_fd)
        _assert_original_root(target, root_fd)
        verified = verify_exported_package(
            target, expected_manifest_sha256=expected_manifest_sha256,
            authorized=True,
        )
        if verified.get("verified_files") != inspected["archived_files"]:
            raise OfflineSourceInstallError("installed source inventory changed")
        _assert_original_root(target, root_fd)
        os.fsync(parent_fd)
        return {
            "schema": SCHEMA,
            "status": "offline_source_installed_playable_release_blocked",
            "install_directory": str(target),
            "archive_sha256": expected_archive_sha256,
            "manifest_sha256": expected_manifest_sha256,
            "project_id": verified["project_id"],
            "world_digest": verified["world_digest"],
            "installed_files": verified["verified_files"],
            "offline_gameplay_reexecuted": True,
            "source_installation_verified": True,
            "model_inference_observed": False,
            "native_device_qualified": False,
            "rights_certified": False,
            "package_signed": False,
            "release_certified": False,
        }
    except OSError as exc:
        raise OfflineSourceInstallError(
            "offline installation failed; reserved destination requires quarantine"
        ) from exc
    finally:
        if root_fd is not None:
            os.close(root_fd)
        os.close(parent_fd)


def _stat_identity(parent_fd: int, name: str) -> tuple[int, int]:
    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode):
        raise OfflineSourceInstallError("reserved installation root changed")
    return info.st_dev, info.st_ino


PREFLIGHT_SCHEMA = "skeleton.app.offline_source_install_preflight.v1"


def preflight_offline_game_install(
    archive: str | Path, destination: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Read-only install admission; does not reserve the destination.

    The installer MUST still repeat all checks and atomically reserve with
    mkdir. This is operator-facing diagnostic evidence, not an admission
    lease, a rollback, or a consumer-release qualification.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    before = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    target, parent_fd = _parent(destination)
    try:
        initial = os.fstat(parent_fd)
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OfflineSourceInstallError(
                "installation destination already exists; never overwrite"
            )
        _assert_original_root(target.parent, parent_fd)
        final = os.fstat(parent_fd)
        identity = lambda item: (
            item.st_dev, item.st_ino, item.st_uid, item.st_mode,
            item.st_mtime_ns, item.st_ctime_ns,
        )
        if identity(initial) != identity(final):
            raise OfflineSourceInstallError(
                "installation parent changed during preflight"
            )
    finally:
        os.close(parent_fd)
    after = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    if before != after or after.get("archive_integrity_verified") is not True:
        raise OfflineSourceInstallError(
            "archive changed during installation preflight"
        )
    return {
        "schema": PREFLIGHT_SCHEMA,
        "status": "offline_install_preflight_ready_unreserved_release_blocked",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "archived_files": after["archived_files"],
        "archive_integrity_verified": True,
        "destination_available_at_inspection": True,
        "destination_reserved": False,
        "source_installation_verified": False,
        "offline_gameplay_reexecuted": False,
        "read_only": True,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


__all__ = [
    "SCHEMA", "PREFLIGHT_SCHEMA", "OfflineSourceInstallError",
    "install_offline_game_source", "preflight_offline_game_install",
]
