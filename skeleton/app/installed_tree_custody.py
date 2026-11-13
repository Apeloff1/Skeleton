"""Bounded descriptor-anchored inode inventory for installed original games.

This records a point-in-time inode identity for every canonical package file
and directory. It does not lock the filesystem or replace content verification.
The canonical game verifier must still compare all bytes with independent pins.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from skeleton.ai.game_builder.dual_runtime_verify import (
    _assert_original_root, _bounded_names, _flags, _parts, _root_fd,
)

MAX_FILES = 128
MAX_ENTRIES = MAX_FILES * 3
MAX_BYTES = 2_100_000
MAX_DEPTH = 8
SCHEMA = "skeleton.app.installed_tree_inode_snapshot.v1"


class InstalledTreeCustodyError(ValueError):
    """Installed asset identity changed or exceeded the bounded trust envelope."""


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def _safe(info: os.stat_result, *, directory: bool) -> None:
    if (info.st_uid != os.geteuid() or info.st_mode & 0o022
            or (not stat.S_ISDIR(info.st_mode) if directory
                else not stat.S_ISREG(info.st_mode))
            or (not directory and info.st_nlink != 1)):
        raise InstalledTreeCustodyError("unsafe installed package inode")


def snapshot_installed_tree(root: str | Path) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Inventory all nested package inodes through nofollow directory handles.

    The bounded inventory is checked for entry-name changes while walking.
    Every child is opened relative to a verified parent, compared to lstat,
    then checked again after use. It rejects symlinks, hardlinked files,
    special files, oversized trees, and non-owner-controlled assets.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise InstalledTreeCustodyError("POSIX nofollow custody required")
    if not (type(root) is str or isinstance(root, Path)):
        raise InstalledTreeCustodyError("concrete installed root path required")
    root_fd = _root_fd(root)
    entries: list[tuple[str, tuple[int, ...]]] = []
    files = 0
    total = 0

    def visit(fd: int, parts: tuple[str, ...]) -> None:
        nonlocal files, total
        info = os.fstat(fd)
        _safe(info, directory=True)
        if len(parts) > MAX_DEPTH:
            raise InstalledTreeCustodyError("installed directory depth exceeded")
        before = _identity(info)
        names = _bounded_names(fd, MAX_ENTRIES + 1)
        if len(names) + len(entries) > MAX_ENTRIES:
            raise InstalledTreeCustodyError("installed tree entry budget exceeded")
        for name in sorted(names):
            path_parts = parts + (name,)
            relative = "/".join(path_parts)
            _parts(relative)
            initial = os.stat(name, dir_fd=fd, follow_symlinks=False)
            directory = stat.S_ISDIR(initial.st_mode)
            _safe(initial, directory=directory)
            child = os.open(name, _flags(directory), dir_fd=fd)
            try:
                opened = os.fstat(child)
                if _identity(opened) != _identity(initial):
                    raise InstalledTreeCustodyError(
                        "installed inode replaced between stat and open"
                    )
                if directory:
                    visit(child, path_parts)
                else:
                    files += 1
                    total += opened.st_size
                    if (files > MAX_FILES or opened.st_size < 0
                            or total > MAX_BYTES):
                        raise InstalledTreeCustodyError(
                            "installed package file or byte budget exceeded"
                        )
                if _identity(os.fstat(child)) != _identity(opened):
                    raise InstalledTreeCustodyError(
                        "installed inode modified while inspecting"
                    )
            finally:
                os.close(child)
            final = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if _identity(final) != _identity(initial):
                raise InstalledTreeCustodyError(
                    "installed entry replaced during inventory"
                )
            entries.append((relative, _identity(final)))
            if len(entries) > MAX_ENTRIES:
                raise InstalledTreeCustodyError(
                    "installed tree entry budget exceeded"
                )
        # os.scandir(fd) may advance the shared directory stream offset.
        # Reopen "." relative to the pinned descriptor for an independent
        # directory stream rather than trusting a second scan on the same fd.
        reopened = os.open(".", _flags(True), dir_fd=fd)
        try:
            if _identity(os.fstat(reopened)) != before:
                raise InstalledTreeCustodyError(
                    "installed directory replaced during inventory"
                )
            final_names = _bounded_names(reopened, MAX_ENTRIES + 1)
        finally:
            os.close(reopened)
        if (tuple(sorted(final_names)) != tuple(sorted(names))
                or _identity(os.fstat(fd)) != before):
            raise InstalledTreeCustodyError(
                "installed directory changed during inventory"
            )

    try:
        original = _identity(os.fstat(root_fd))
        _assert_original_root(root, root_fd)
        visit(root_fd, ())
        _assert_original_root(root, root_fd)
        if _identity(os.fstat(root_fd)) != original:
            raise InstalledTreeCustodyError(
                "installed root inode changed during inventory"
            )
        if not 1 <= files <= MAX_FILES:
            raise InstalledTreeCustodyError("installed package has no bounded files")
        return tuple(sorted((("", original), *entries)))
    finally:
        os.close(root_fd)


def installed_tree_snapshot_digest(
    snapshot: tuple[tuple[str, tuple[int, ...]], ...],
) -> str:
    """Stable digest for a specific observed inventory, not a device signature."""
    if (type(snapshot) is not tuple
            or not snapshot
            or any(type(item) is not tuple or len(item) != 2
                   or type(item[0]) is not str or type(item[1]) is not tuple
                   or any(type(part) is not int for part in item[1])
                   for item in snapshot)):
        raise InstalledTreeCustodyError("invalid installed inode inventory")
    raw = json.dumps(
        {"schema": SCHEMA, "entries": snapshot},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()


__all__ = [
    "SCHEMA", "MAX_FILES", "MAX_ENTRIES", "MAX_BYTES",
    "InstalledTreeCustodyError", "snapshot_installed_tree",
    "installed_tree_snapshot_digest",
]
