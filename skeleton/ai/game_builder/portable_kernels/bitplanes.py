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


def encode_nes_2bpp(tile: Sequence[Sequence[int]]) -> bytes:
    """Encode the NES CHR planar byte order: eight low rows, eight high rows."""
    rows = _pixels(tile, 3)
    return bytes(sum(((row[x] >> plane) & 1) << (7-x) for x in range(8))
                 for plane in (0, 1) for row in rows)


def decode_nes_2bpp(data: bytes) -> tuple[tuple[int, ...], ...]:
    """Invert authentic NES 16-byte planar CHR tiles."""
    raw = _raw(data, 16)
    return tuple(tuple(((raw[y] >> (7-x)) & 1) |
                       (((raw[8+y] >> (7-x)) & 1) << 1)
                       for x in range(8)) for y in range(8))


def encode_snes_4bpp(tile: Sequence[Sequence[int]]) -> bytes:
    """Encode SNES 4bpp: planes 0-1 row-interleaved, then planes 2-3."""
    rows = _pixels(tile, 15)
    return bytes(sum(((row[x] >> plane) & 1) << (7-x) for x in range(8))
                 for pair in (0, 2) for row in rows for plane in (pair, pair+1))


def decode_snes_4bpp(data: bytes) -> tuple[tuple[int, ...], ...]:
    """Decode both SNES 16-byte interleaved plane banks into palette indices."""
    raw = _raw(data, 32)
    return tuple(tuple(sum(((raw[(plane//2)*16+y*2+(plane%2)] >> (7-x)) & 1) << plane
                           for plane in range(4))
                       for x in range(8)) for y in range(8))


def encode_sms_4bpp(tile: Sequence[Sequence[int]]) -> bytes:
    """Sega Master System/Game Gear Mode 4: four bitplanes per scanline."""
    rows = _pixels(tile, 15)
    return bytes(sum(((row[x] >> plane) & 1) << (7-x) for x in range(8))
                 for row in rows for plane in range(4))


def decode_sms_4bpp(data: bytes) -> tuple[tuple[int, ...], ...]:
    """Round-trip four Sega VDP row bitplanes with strict 32-byte admission."""
    raw = _raw(data, 32)
    return tuple(tuple(sum(((raw[y*4+plane] >> (7-x)) & 1) << plane
                           for plane in range(4))
                       for x in range(8)) for y in range(8))


def encode_genesis_4bpp(tile: Sequence[Sequence[int]]) -> bytes:
    """Mega Drive/Genesis packed 4bpp, high nibble for left pixel."""
    rows = _pixels(tile, 15)
    return bytes((row[x] << 4) | row[x+1] for row in rows for x in range(0,8,2))

