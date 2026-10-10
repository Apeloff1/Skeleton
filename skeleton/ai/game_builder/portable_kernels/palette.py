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


def encode_rgb332(pixel: object) -> int:
    """8-bit RGB332 packed display palette: 3R, 3G, 2B."""
    r,g,b=_rgb(pixel)
    return ((r*7+127)//255)<<5 | ((g*7+127)//255)<<2 | ((b*3+127)//255)


def decode_rgb332(word: object) -> tuple[int,int,int]:
    """Expand 8-bit RGB332 into working RGB with deterministic rounding."""
    n=_packed(word,255)
    return ((((n>>5)&7)*255+3)//7,
            (((n>>2)&7)*255+3)//7,
            ((n&3)*255+1)//3)


def nearest_palette_index(pixel: object, colors: object) -> int:
    """Deterministic weighted RGB nearest-neighbor with stable tie breaking."""
    r,g,b=_rgb(pixel)
    palette=_palette(colors)
    return min(range(len(palette)),key=lambda i:
               (3*(r-palette[i][0])**2 + 4*(g-palette[i][1])**2 +
                2*(b-palette[i][2])**2,i))


def index_image(rows: object, colors: object) -> tuple[tuple[int,...],...]:
    """Palettize a bounded RGB framebuffer; no implicit lossy resize or crop."""
    palette=_palette(colors)
    if (not isinstance(rows,(tuple,list)) or not 1<=len(rows)<=64
            or not isinstance(rows[0],(tuple,list)) or not 1<=len(rows[0])<=64
            or any(not isinstance(row,(tuple,list)) or len(row)!=len(rows[0])
                   for row in rows)):
        raise PaletteError("indexed framebuffer must be rectangular within 64x64")
    return tuple(tuple(nearest_palette_index(pixel,palette) for pixel in row)
                 for row in rows)

