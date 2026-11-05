"""Descriptor-anchored, bounded, read-only evidence intake.

Callers must already own a trusted private directory descriptor. No path
resolution, recursive traversal, symlink following or unchecked whole-file read.
"""
from __future__ import annotations

import os
import re
import stat

from .contracts import strict_integer
from .errors import deny

_LEAF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z", re.ASCII)


def require_leaf(leaf: object) -> str:
    if type(leaf) is not str or _LEAF.fullmatch(leaf) is None:
        deny("workspace-leaf")
    if leaf in (".", ".."):
        deny("workspace-traversal")
    return leaf


def read_private_leaf(root_fd: int, leaf: str, *, max_bytes: int = 1048576) -> bytes:
    require_leaf(leaf)
    strict_integer(max_bytes, minimum=1, maximum=1048576, field="workspace-budget")
    if type(root_fd) is not int or root_fd < 0:
        deny("workspace-descriptor")
    root = os.fstat(root_fd)
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.geteuid() or root.st_mode & 0o077:
        deny("workspace-root")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    try:
        fd = os.open(leaf, flags, dir_fd=root_fd)
    except OSError:
        deny("workspace-open")
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            deny("workspace-nonregular")
        if before.st_uid != os.geteuid() or before.st_mode & 0o077:
            deny("workspace-permission")
        if not 0 <= before.st_size <= max_bytes:
            deny("workspace-oversize")
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:
            data = os.read(fd, min(65536, max_bytes + 1 - total))
            if not data:
                break
            total += len(data)
            chunks.append(data)
        after = os.fstat(fd)
        if total > max_bytes or total != before.st_size:
            deny("workspace-oversize")
        if ((before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns)
                != (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns)):
            deny("workspace-mutation")
        return b"".join(chunks)
    finally:
        os.close(fd)
