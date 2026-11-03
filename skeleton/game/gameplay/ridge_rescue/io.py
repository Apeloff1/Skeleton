"""Bounded local file IO for CLI. Export is create-only and never follows final symlinks."""
from __future__ import annotations
import os
import stat
from pathlib import Path
from .custody import canonical

class IOErrorBounded(ValueError):
    pass

def read_bounded(path: str | Path, limit: int = 256_000) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise IOErrorBounded("input must be a bounded regular file")
            data = os.read(fd, limit + 1)
            if len(data) > limit:
                raise IOErrorBounded("input exceeds byte limit")
            return data
        finally:
            os.close(fd)
    except OSError as exc:
        raise IOErrorBounded("input open refused") from exc

def write_new(path: str | Path, value: object, limit: int = 256_000) -> None:
    payload = canonical(value) + b"\n"
    if len(payload) > limit:
        raise IOErrorBounded("output exceeds byte limit")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise IOErrorBounded("refuse overwrite or unsafe output") from exc
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
