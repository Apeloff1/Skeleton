"""Godot ``.pck`` pack header reader (GFX-07).

Godot 4 PCK layout (little endian): magic ``GDPC``; u32 pack format version;
u32 engine major, minor, patch; then (format>=2) u32 flags and u64 file base
offset; 16 reserved u32; u32 file count; followed by the directory.
Packs embedded in executables are located via a trailing ``GDPC`` footer.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"GDPC"


class PckError(ValueError):
    pass


@dataclass(frozen=True)
class PckHeader:
    format_version: int
    engine: tuple[int, int, int]
    flags: int
    file_base: int
    file_count: int
    offset: int = 0

    @property
    def encrypted_dir(self) -> bool:
        return bool(self.flags & 1)


def parse_header(data: bytes, offset: int = 0) -> PckHeader:
    if data[offset:offset + 4] != MAGIC:
        raise PckError("missing GDPC magic")
    pos = offset + 4
    try:
        fmt, major, minor, patch = struct.unpack_from("<4I", data, pos)
        pos += 16
        flags = 0
        base = 0
        if fmt >= 2:
            flags, base = struct.unpack_from("<IQ", data, pos)
            pos += 12
        pos += 16 * 4
        (count,) = struct.unpack_from("<I", data, pos)
    except struct.error as exc:
        raise PckError("truncated header") from exc
    if fmt not in (1, 2, 3):
        raise PckError(f"unsupported pack format {fmt}")
    return PckHeader(fmt, (major, minor, patch), flags, base, count, offset)


def find_embedded(data: bytes) -> int | None:
    """Return offset of a pack embedded in an executable, via its footer."""
    if len(data) < 12 or data[-4:] != MAGIC:
        return None
    (size,) = struct.unpack_from("<Q", data, len(data) - 12)
    start = len(data) - 12 - size
    if start < 0 or data[start:start + 4] != MAGIC:
        return None
    return start


def read(path: Path) -> PckHeader:
    data = path.read_bytes()
    if data[:4] == MAGIC:
        return parse_header(data)
    off = find_embedded(data)
    if off is None:
        raise PckError(f"no pack in {path.name}")
    return parse_header(data, off)


def build_header(engine: tuple[int, int, int], file_count: int, fmt: int = 2, flags: int = 0, base: int = 0) -> bytes:
    """Construct a minimal header (used by fixtures and tests)."""
    out = MAGIC + struct.pack("<4I", fmt, *engine)
    if fmt >= 2:
        out += struct.pack("<IQ", flags, base)
    out += b"\0" * 64 + struct.pack("<I", file_count)
    return out
