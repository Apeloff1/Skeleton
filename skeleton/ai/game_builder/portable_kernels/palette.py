"""Loss-aware, bounded native RGB palette conversion for original homebrew art."""
from __future__ import annotations
from collections.abc import Sequence

class PaletteError(ValueError):
    """Palette, pixel or framebuffer admission failed."""

def _rgb(pixel: object) -> tuple[int, int, int]:
    if (not isinstance(pixel, (tuple, list)) or len(pixel) != 3
            or any(type(c) is not int or not 0 <= c <= 255 for c in pixel)):
        raise PaletteError("RGB requires three exact 8-bit channels")
    return tuple(pixel)

def _packed(value: object, limit: int) -> int:
    if type(value) is not int or not 0 <= value <= limit:
        raise PaletteError("packed color exceeds target hardware depth")
    return value

def _palette(colors: object) -> tuple[tuple[int,int,int],...]:
    if not isinstance(colors, (tuple,list)) or not 1 <= len(colors) <= 256:
        raise PaletteError("palette requires one to 256 colors")
    return tuple(_rgb(color) for color in colors)


def encode_rgb555(pixel: object) -> int:
    """15-bit BGR555 word as consumed by many handheld and console palettes."""
    r,g,b = _rgb(pixel)
    q = lambda c: (c*31 + 127)//255
    return q(r) | (q(g)<<5) | (q(b)<<10)

