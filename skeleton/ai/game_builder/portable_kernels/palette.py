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


def decode_rgb555(word: object) -> tuple[int,int,int]:
    """Expand five-bit component words back to bounded 8-bit working RGB."""
    n = _packed(word,0x7fff)
    q = lambda x: (x*255+15)//31
    return q(n&31),q((n>>5)&31),q((n>>10)&31)


def encode_rgb565(pixel: object) -> int:
    """16-bit RGB565 with six green bits for desktop and embedded displays."""
    r,g,b = _rgb(pixel)
    return ((r*31+127)//255)<<11 | ((g*63+127)//255)<<5 | ((b*31+127)//255)


def decode_rgb565(word: object) -> tuple[int,int,int]:
    """Decode RGB565 without accidentally swapping red and blue channels."""
    n=_packed(word,0xffff)
    return (((n>>11)&31)*255+15)//31, (((n>>5)&63)*255+31)//63, ((n&31)*255+15)//31

