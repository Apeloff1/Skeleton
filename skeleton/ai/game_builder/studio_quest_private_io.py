"""Bounded descriptor-anchored private JSON custody for Studio A CLI edits.

The file and each ancestor are opened without following symlinks. File
identity, size, permissions and parent-directory identity are checked after
the bounded read; duplicate keys and nonfinite JSON are rejected. This is
local operator input, not a signature or proof of external authorship.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _open_directory

MAX_PRIVATE_JSON_BYTES = 65536


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def read_studio_private_json(path: Path, limit: int) -> dict[str, Any]:
    """Reject hostile links, mutable reads, stale parent paths and JSON aliases."""
    if (not isinstance(path, Path) or path.name in ("", ".", "..")
            or type(limit) is not int
            or not 0 < limit <= MAX_PRIVATE_JSON_BYTES):
        raise StudioQuestError("invalid bounded Studio A JSON source")
    try:
        if len(str(path).encode("utf-8", "strict")) > 4096:
            raise StudioQuestError("Studio A JSON path exceeds byte budget")
    except UnicodeError as exc:
        raise StudioQuestError("invalid Studio A JSON path Unicode") from exc
    parent_fd = _open_directory(path.parent)
    try:
        original_parent = os.fstat(parent_fd)
        if not stat.S_ISDIR(original_parent.st_mode):
            raise StudioQuestError("Studio A JSON parent is not a directory")
        flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 getattr(os, "O_CLOEXEC", 0))
        fd = os.open(path.name, flags, dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= limit
                    or (os.name == "posix" and (
                        before.st_uid != os.getuid()
                        or before.st_mode & 0o077
                        or before.st_nlink != 1))):
                raise StudioQuestError("Studio A JSON must be a private regular file")
            raw = os.read(fd, limit + 1)
            after = os.fstat(fd)
            if (len(raw) != before.st_size
                    or _identity(before) != _identity(after)):
                raise StudioQuestError("Studio A JSON changed during descriptor read")
        finally:
            os.close(fd)
        # A directory swap after the original open must not silently turn an
        # old directory's file into an approved input for the new path.
        check_fd = _open_directory(path.parent)
        try:
            checked_parent = os.fstat(check_fd)
            if ((original_parent.st_dev, original_parent.st_ino) !=
                    (checked_parent.st_dev, checked_parent.st_ino)):
                raise StudioQuestError("Studio A JSON parent directory was replaced")
        finally:
            os.close(check_fd)
    finally:
        os.close(parent_fd)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate Studio A JSON key")
            result[key] = value
        return result

    try:
        result = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite Studio A JSON value")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid Studio A JSON document") from exc
    if type(result) is not dict:
        raise StudioQuestError("Studio A JSON root must be an object")
    return result
