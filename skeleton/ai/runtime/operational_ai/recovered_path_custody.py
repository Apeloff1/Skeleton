"""Private directory custody for recovered native qualification and training.

Use the canonical model root opener for ancestry, then create only one leaf
relative to the already-open trusted parent. Never weaken the GGUF path guard.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .model.gguf.file_guard import open_trusted_root


def require_absolute_directory(directory: Path) -> Path:
    """Accept normal concrete pathlib paths, not strings or traversal."""
    if not isinstance(directory, Path) or not directory.is_absolute():
        raise ValueError("absolute pathlib directory required")
    if directory == directory.parent or directory.name in ("", ".", "..") or ".." in directory.parts:
        raise ValueError("non-root directory without traversal required")
    return directory


def open_private_directory(directory: Path, *, create: bool) -> int:
    """Return caller-owned no-follow descriptor, or raise before unsafe writes.

    Creation is opt-in, immediate-parent only, and unsupported without POSIX
    directory descriptors. The target may already exist, but must be an owned
    private directory; symlinks and group/world access never qualify.
    """
    path = require_absolute_directory(directory)
    if type(create) is not bool:
        raise ValueError("explicit create flag required")
    if os.name != "posix" or not all(hasattr(os, x) for x in ("O_DIRECTORY", "O_NOFOLLOW", "geteuid")):
        raise ValueError("private directory custody requires POSIX descriptors")
    parent = open_trusted_root(path.parent)
    child = None
    try:
        if create:
            try:
                os.mkdir(path.name, mode=0o700, dir_fd=parent)
            except FileExistsError:
                pass
        child = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        metadata = os.fstat(child)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_uid != os.geteuid():
            raise ValueError("directory is not exclusively owner-private")
        if create:
            os.fsync(parent)
        result, child = child, None
        return result
    finally:
        if child is not None:
            os.close(child)
        os.close(parent)
