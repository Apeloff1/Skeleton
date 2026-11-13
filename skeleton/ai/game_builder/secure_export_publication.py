"""Descriptor-anchored, no-clobber publication of generated game source trees.

This is a local filesystem integrity boundary, not a package signature, a
native build, a rights clearance, or a device qualification. Unsupported POSIX
atomic-rename primitives fail closed instead of silently replacing a directory.
"""
from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Mapping

from .dual_runtime_verify import _assert_original_root, _flags, _root_fd


class AtomicDirectoryPublicationError(ValueError):
    """A generated source tree could not be published without clobbering."""


def _rename_noreplace(parent_fd: int, source: str, destination: str) -> None:
    """Rename within one pinned directory without ever replacing a target."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux"):
        operation = getattr(libc, "renameat2", None)
        if operation is None:
            raise AtomicDirectoryPublicationError("renameat2 unavailable")
        operation.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_uint,
        )
        operation.restype = ctypes.c_int
        result = operation(
            parent_fd, os.fsencode(source), parent_fd,
            os.fsencode(destination), 1,  # RENAME_NOREPLACE
        )
    elif sys.platform == "darwin":
        operation = getattr(libc, "renameatx_np", None)
        if operation is None:
            raise AtomicDirectoryPublicationError("renameatx_np unavailable")
        operation.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_uint,
        )
        operation.restype = ctypes.c_int
        result = operation(
            parent_fd, os.fsencode(source), parent_fd,
            os.fsencode(destination), 4,  # RENAME_EXCL
        )
    else:
        raise AtomicDirectoryPublicationError(
            "atomic no-replace directory publication unsupported on this POSIX host"
        )
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), destination)


def _remove_contents(directory_fd: int) -> None:
    """Remove only entries below an already-open, private staging directory."""
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            info = os.stat(
                entry.name, dir_fd=directory_fd, follow_symlinks=False,
            )
            if stat.S_ISDIR(info.st_mode):
                child_fd = os.open(
                    entry.name, _flags(True), dir_fd=directory_fd,
                )
                try:
                    _remove_contents(child_fd)
                finally:
                    os.close(child_fd)
                os.rmdir(entry.name, dir_fd=directory_fd)
            else:
                os.unlink(entry.name, dir_fd=directory_fd)


def _write_one(stage_fd: int, relative: str, payload: bytes) -> None:
    if (
        type(relative) is not str
        or not relative
        or len(relative) > 512
        or relative.startswith("/")
        or "\\" in relative
        or len(relative.split("/")) > 8
        or any(len(part) > 127 or part in ("", ".", "..", ".git")
               for part in relative.split("/"))
        or type(payload) is not bytes
    ):
        raise AtomicDirectoryPublicationError("invalid generated source entry")
    parts = relative.split("/")
    current = os.dup(stage_fd)
    try:
        for component in parts[:-1]:
            try:
                os.mkdir(component, 0o700, dir_fd=current)
            except FileExistsError:
                pass
            following = os.open(
                component, _flags(True), dir_fd=current,
            )
            os.close(current)
            current = following
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        fd = os.open(parts[-1], flags, 0o600, dir_fd=current)
        try:
            position = 0
            while position < len(payload):
                written = os.write(fd, payload[position:])
                if written <= 0:
                    raise AtomicDirectoryPublicationError("source write stalled")
                position += written
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(current)
    finally:
        os.close(current)



def preflight_generated_tree_destination(destination: str | Path) -> Path:
    """Reject predictable unsafe export targets before game construction.

    This read-only check is not a lock or permission to publish. The atomic
    publisher rechecks the pinned parent and performs no-replace publication.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise AtomicDirectoryPublicationError(
            "descriptor-safe source publication requires POSIX O_NOFOLLOW"
        )
    target = Path(destination).expanduser().absolute()
    if target.name in ("", ".", "..") or len(target.name) > 127:
        raise AtomicDirectoryPublicationError("invalid destination name")
    try:
        parent_fd = _root_fd(target.parent)
    except (OSError, TypeError, ValueError) as exc:
        raise AtomicDirectoryPublicationError("unsafe destination parent") from exc
    try:
        parent = os.fstat(parent_fd)
        if (not stat.S_ISDIR(parent.st_mode)
                or parent.st_uid != os.geteuid()
                or parent.st_mode & 0o022):
            raise AtomicDirectoryPublicationError(
                "destination parent must be private and operator-owned"
            )
        _assert_original_root(target.parent, parent_fd)
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise AtomicDirectoryPublicationError("game export already exists")
        _assert_original_root(target.parent, parent_fd)
    except (OSError, ValueError) as exc:
        if isinstance(exc, AtomicDirectoryPublicationError):
            raise
        raise AtomicDirectoryPublicationError(
            "unsafe game export destination"
        ) from exc
    finally:
        os.close(parent_fd)
    return target


def publish_generated_tree(
    files: Mapping[str, bytes], destination: str | Path,
) -> Path:
    """Publish a fully fsynced game tree, atomically, without replacing a path.

    A private staging directory is addressed only through directory handles.
    The final no-replace rename is relative to the pinned parent handle.
    On any failure, only the staging inode we created may be removed.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise AtomicDirectoryPublicationError(
            "descriptor-safe source publication requires POSIX O_NOFOLLOW"
        )
    if not isinstance(files, dict) or not files or len(files) > 128:
        raise AtomicDirectoryPublicationError("invalid generated source inventory")
    if any(type(payload) is not bytes for payload in files.values()):
        raise AtomicDirectoryPublicationError("generated source must contain only bytes")
    if sum(len(payload) for payload in files.values()) > 2_100_000:
        raise AtomicDirectoryPublicationError("generated source exceeds 2.1 MB budget")
    target = Path(destination).expanduser().absolute()
    if target.name in ("", ".", "..") or len(target.name) > 127:
        raise AtomicDirectoryPublicationError("invalid destination name")
    try:
        parent_fd = _root_fd(target.parent)
    except (OSError, TypeError, ValueError) as exc:
        raise AtomicDirectoryPublicationError("unsafe destination parent") from exc
    stage_name = ".game-export-" + secrets.token_hex(16)
    stage_fd = -1
    created = False
    published = False
    identity: tuple[int, int] | None = None
    try:
        parent = os.fstat(parent_fd)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or parent.st_mode & 0o022
        ):
            raise AtomicDirectoryPublicationError(
                "destination parent must be private and operator-owned"
            )
        _assert_original_root(target.parent, parent_fd)
        os.mkdir(stage_name, 0o700, dir_fd=parent_fd)
        created = True
        stage_fd = os.open(stage_name, _flags(True), dir_fd=parent_fd)
        stage_info = os.fstat(stage_fd)
        identity = (stage_info.st_dev, stage_info.st_ino)
        for relative, payload in sorted(files.items()):
            _write_one(stage_fd, relative, payload)
        os.fsync(stage_fd)
        _assert_original_root(target.parent, parent_fd)
        before = os.stat(
            stage_name, dir_fd=parent_fd, follow_symlinks=False,
        )
        if (before.st_dev, before.st_ino) != identity:
            raise AtomicDirectoryPublicationError("staging directory was replaced")
        _rename_noreplace(parent_fd, stage_name, target.name)
        published = True
        final = os.stat(
            target.name, dir_fd=parent_fd, follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(final.st_mode)
            or (final.st_dev, final.st_ino) != identity
        ):
            raise AtomicDirectoryPublicationError("published directory changed")
        os.fsync(parent_fd)
        _assert_original_root(target.parent, parent_fd)
        return target
    except (OSError, ValueError) as exc:
        if isinstance(exc, AtomicDirectoryPublicationError):
            raise
        raise AtomicDirectoryPublicationError(
            "atomic game-source publication failed"
        ) from exc
    finally:
        if created and stage_fd < 0:
            try:
                os.rmdir(stage_name, dir_fd=parent_fd)
            except OSError:
                pass
        if created and stage_fd >= 0 and identity is not None:
            name = target.name if published else stage_name
            try:
                observed = os.stat(
                    name, dir_fd=parent_fd, follow_symlinks=False,
                )
                if (observed.st_dev, observed.st_ino) == identity and not (
                    published and sys.exc_info()[0] is None
                ):
                    _remove_contents(stage_fd)
                    os.rmdir(name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
            except OSError:
                pass
        if stage_fd >= 0:
            os.close(stage_fd)
        os.close(parent_fd)


__all__ = [
    "AtomicDirectoryPublicationError", "preflight_generated_tree_destination",
    "publish_generated_tree",
]
