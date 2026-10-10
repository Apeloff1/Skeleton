"""Deterministic 8×8 native tile codecs for original homebrew assets.

Only pixel indices are accepted; no ROM extraction, game copying, firmware,
or release certification is performed. Layouts follow hardware bitplane order.
"""
from __future__ import annotations
from collections.abc import Sequence

class PortableCodecError(ValueError):
    """Malformed or out-of-budget native tile data."""

def _pixels(tile: Sequence[Sequence[int]], highest: int) -> tuple[tuple[int, ...], ...]:
    if not isinstance(tile, (tuple, list)) or len(tile) != 8:
        raise PortableCodecError("an indexed tile must contain exactly eight rows")
    if any(not isinstance(row, (tuple, list)) or len(row) != 8
           or any(type(pixel) is not int or not 0 <= pixel <= highest for pixel in row)
           for row in tile):
        raise PortableCodecError("tile indices exceed palette depth or tile geometry")
    return tuple(tuple(row) for row in tile)

def _raw(data: bytes, size: int) -> bytes:
    if type(data) is not bytes or len(data) != size:
        raise PortableCodecError(f"native tile must contain exactly {size} bytes")
    return data


def encode_gb_2bpp(tile: Sequence[Sequence[int]]) -> bytes:
    """Encode eight indexed pixels per row to DMG/CGB low/high interleaved 2bpp."""
    rows = _pixels(tile, 3)
    out = bytearray()
    for row in rows:
        for plane in (0, 1):
            out.append(sum(((pixel >> plane) & 1) << (7 - x) for x, pixel in enumerate(row)))
    return bytes(out)


def decode_gb_2bpp(data: bytes) -> tuple[tuple[int, ...], ...]:
    """Invert the 16-byte Game Boy 2bpp bitplane layout exactly."""
    raw = _raw(data, 16)
    return tuple(tuple(((raw[2*y] >> (7-x)) & 1) |
                       (((raw[2*y+1] >> (7-x)) & 1) << 1)
                       for x in range(8)) for y in range(8))

