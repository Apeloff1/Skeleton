"""Bounded, descriptor-pinned Linux kernel counter reads.

These are observational snapshots, not atomic hardware reservations. No
symlink traversal or non-regular input may grant pressure recovery.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat

from .offline_cpu_thermal import _open_pinned_root

MAX_KERNEL_COUNTER = (1 << 64) - 1
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,19})")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


def uint_counter(value: str) -> int:
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise ValueError("invalid kernel counter")
    number = int(value)
    if number > MAX_KERNEL_COUNTER:
        raise ValueError("kernel counter exceeds range")
    return number


def read_kernel_ascii(path: str | Path, *, maximum: int) -> str:
    if type(maximum) is not int or not 1 <= maximum <= 64 * 1024:
        raise ValueError("invalid kernel read bound")
    raw_path = os.fspath(path)
    if (type(raw_path) is not str or not raw_path.startswith("/")
            or len(raw_path) > 4096 or "\x00" in raw_path
            or any(part in (".", "..") for part in raw_path.split("/"))):
        raise ValueError("invalid kernel counter path")
    parent, name = os.path.split(raw_path)
    if not name:
        raise ValueError("kernel counter filename required")
    directory = _open_pinned_root(parent)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW
                     | getattr(os, "O_NONBLOCK", 0)
                     | getattr(os, "O_CLOEXEC", 0), dir_fd=directory)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("kernel counter is not regular")
            data = bytearray()
            while len(data) <= maximum:
                chunk = os.read(fd, min(4096, maximum + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            after = os.fstat(fd)
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            identity = lambda item: (item.st_dev, item.st_ino, item.st_mode)
            if not data or len(data) > maximum or identity(before) != identity(after) or identity(after) != identity(current):
                raise ValueError("kernel counter changed or exceeded read bound")
            fresh = _open_pinned_root(parent)
            try:
                if identity(os.fstat(fresh)) != identity(os.fstat(directory)):
                    raise ValueError("kernel counter directory changed")
            finally:
                os.close(fresh)
            return data.decode("ascii", errors="strict")
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def parse_counter_table(raw: str, *, selected: frozenset[str] | None = None) -> dict[str, int]:
    result: dict[str, int] = {}
    seen: set[str] = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != 2 or _NAME.fullmatch(fields[0]) is None or fields[0] in seen:
            raise ValueError("malformed or duplicate kernel counter")
        name, value = fields
        seen.add(name)
        if selected is None or name in selected:
            result[name] = uint_counter(value)
    if not result:
        raise ValueError("no usable kernel counters")
    return result
