"""Private canonical receipts shared by offline Mongo relocation and cutover.

This receipt-only dependency does not import the SQLite graph deployment stack.
Local operator custody is required; the receipt is an integrity witness, not
a remote signature or evidence that all application writers have stopped.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

MAX_MANIFEST = 128 * 1024


class DeploymentHeld(RuntimeError):
    pass


def _ack(value):
    if value is not True:
        raise DeploymentHeld("stop all application and old writers; explicit acknowledgement required")


def _dir(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise DeploymentHeld("absolute private directory required")
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or (os.name == "posix" and
            (info.st_uid != os.getuid() or info.st_mode & 0o077)):
        raise DeploymentHeld("private directory required")
    return path


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode()


def _file_check(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            (os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077))):
        raise DeploymentHeld("private single-link receipt required")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _read_json(path):
    path = Path(path)
    _dir(path.parent)
    before = _file_check(path.lstat())
    if before[2] > MAX_MANIFEST:
        raise DeploymentHeld("receipt byte bound")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    try:
        if _file_check(os.fstat(fd)) != before:
            raise DeploymentHeld("receipt replaced before read")
        with os.fdopen(fd, "rb") as src:
            fd = -1
            raw = src.read(MAX_MANIFEST + 1)
            if _file_check(os.fstat(src.fileno())) != before:
                raise DeploymentHeld("receipt changed during read")
    finally:
        if fd != -1:
            os.close(fd)
    if _file_check(path.lstat()) != before or not raw or len(raw) > MAX_MANIFEST:
        raise DeploymentHeld("receipt readback differs")
    try:
        value = json.loads(raw)
        canonical = _json(value)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise DeploymentHeld("receipt invalid") from exc
    if canonical != raw:
        raise DeploymentHeld("receipt is not canonical")
    return value


def _new_json(path, value):
    path = Path(path)
    _dir(path.parent)
    raw = _json(value)
    if not raw or len(raw) > MAX_MANIFEST:
        raise DeploymentHeld("receipt byte bound")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            fd = -1
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    if os.name == "posix":
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    if _read_json(path) != value:
        raise DeploymentHeld("published receipt differs")
