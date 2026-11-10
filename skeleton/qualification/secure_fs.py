"""Bounded POSIX descriptor custody for untrusted GF-M JSON inputs.

Never trust a pathname preflight. Directory components, member inodes, and
post-read identities are checked while held open. Other hosts fail closed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

from .errors import SchemaError


def _identity(st: os.stat_result) -> tuple[int, ...]:
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_nlink,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _directory(path: Path) -> int:
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY") or os.open not in os.supports_dir_fd):
        raise SchemaError(str(path), "descriptor-safe source custody unavailable")
    parts = Path(os.path.abspath(os.fspath(path.expanduser()))).parts
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    fd: int | None = None
    try:
        fd = os.open(parts[0], flags)
        for part in parts[1:]:
            nxt = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = nxt
        st = os.fstat(fd)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_mode & 0o022):
            raise SchemaError(str(path), "untrusted source directory permissions")
        held = fd
        fd = None
        return held
    except (OSError, TypeError, ValueError) as exc:
        raise SchemaError(str(path), "unsafe source directory") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _read(fd: int, name: str, where: Path, limit: int) -> bytes:
    if (type(name) is not str or not name.endswith(".json")
            or name in (".", "..") or "/" in name or "\x00" in name
            or len(os.fsencode(name)) > 255):
        raise SchemaError(str(where), "unsafe JSON filename")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    member: int | None = None
    try:
        member = os.open(name, flags, dir_fd=fd)
        before = os.fstat(member)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid() or before.st_mode & 0o022
                or not 0 < before.st_size <= limit):
            raise SchemaError(str(where), "unsafe JSON inode or byte budget")
        left = before.st_size
        chunks: list[bytes] = []
        while left:
            chunk = os.read(member, min(left, 65536))
            if not chunk:
                raise SchemaError(str(where), "JSON truncated during custody read")
            left -= len(chunk)
            chunks.append(chunk)
        if os.read(member, 1) or _identity(os.fstat(member)) != _identity(before):
            raise SchemaError(str(where), "JSON changed during custody read")
        os.close(member)
        member = None
        check = os.open(name, flags, dir_fd=fd)
        try:
            if _identity(os.fstat(check)) != _identity(before):
                raise SchemaError(str(where), "JSON pathname replaced after read")
        finally:
            os.close(check)
        return b"".join(chunks)
    except (OSError, TypeError, ValueError) as exc:
        raise SchemaError(str(where), "unsafe JSON input") from exc
    finally:
        if member is not None:
            os.close(member)


def read_one(path: str | Path, *, limit: int) -> bytes:
    target = Path(path)
    fd = _directory(target.parent)
    try:
        before = _identity(os.fstat(fd))
        raw = _read(fd, target.name, target, limit)
        current = _directory(target.parent)
        try:
            if _identity(os.fstat(current)) != before:
                raise SchemaError(str(target), "JSON parent replaced during read")
        finally:
            os.close(current)
        return raw
    finally:
        os.close(fd)


def read_inventory(directory: str | Path, *, max_files: int,
                   max_bytes: int, max_total: int) -> list[tuple[Path, bytes]]:
    if (any(type(n) is not int for n in (max_files, max_bytes, max_total))
            or min(max_files, max_bytes, max_total) < 1):
        raise ValueError("positive finite inventory limits required")
    root = Path(directory)
    try:
        fd = _directory(root)
    except SchemaError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            return []  # absent evidence is BLOCKED, not a false PASS
        raise
    try:
        before = _identity(os.fstat(fd))
        names: list[str] = []
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    names.append(entry.name)
                    if len(names) > 4 * max_files:
                        raise SchemaError(str(root), "input directory entry budget exceeded")
        except OSError as exc:
            raise SchemaError(str(root), "cannot list bounded input directory") from exc
        selected = sorted(n for n in names if n.endswith(".json"))
        if len(selected) > max_files:
            raise SchemaError(str(root), "JSON file budget exceeded")
        total = 0
        result: list[tuple[Path, bytes]] = []
        for name in selected:
            path = root / name
            raw = _read(fd, name, path, max_bytes)
            total += len(raw)
            if total > max_total:
                raise SchemaError(str(root), "aggregate JSON byte budget exceeded")
            result.append((path, raw))
        if _identity(os.fstat(fd)) != before:
            raise SchemaError(str(root), "input directory changed during scan")
        fresh = _directory(root)
        try:
            if _identity(os.fstat(fresh)) != before:
                raise SchemaError(str(root), "input directory replaced during scan")
        finally:
            os.close(fresh)
        return result
    finally:
        os.close(fd)


def decode(raw: bytes, where: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def invalid_constant(value: str) -> None:
        raise ValueError("nonfinite constant " + value)
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise SchemaError(where, "invalid JSON input") from exc
