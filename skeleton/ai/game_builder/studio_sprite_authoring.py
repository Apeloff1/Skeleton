"""Original artist-authored sprite ingestion for the existing console tile studio.

No external network, AI-image provider, copyright inference or automatic
source edit: only explicit 48x8 RGBA PNG or exact typed 6×64 pixel tiles.
The current native cartridge engines have precisely six semantic 8x8 tiles;
larger atlases require separate bank/engine work and are not silently cropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from skeleton.jeeves.game_console_assets import decode_png

from .contracts import canonical_digest

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SUPPORTED = frozenset({"nearest", "ordered4", "exact"})
_BAYER = (
    (-8, 0, -6, 2),
    (4, -4, 6, -2),
    (-5, 3, -7, 1),
    (7, -1, 5, -3),
)


class StudioSpriteAuthoringError(ValueError):
    """Unapproved, ambiguous or unsupported original image descriptor."""


@dataclass(frozen=True, slots=True)
class ArtistSpriteAtlas:
    tiles: tuple[tuple[int, ...], ...]
    source_sha256: str
    palette_digest: str
    quantization: str
    source_kind: str

    def __post_init__(self) -> None:
        if (type(self.tiles) is not tuple or len(self.tiles) != 6 or
                any(type(tile) is not tuple or len(tile) != 64 or any(
                    type(pixel) is not int or not 0 <= pixel <= 3 for pixel in tile
                ) for tile in self.tiles)):
            raise StudioSpriteAuthoringError("six exact 8x8 original indexed sprites required")
        if (type(self.source_sha256) is not str or _SHA.fullmatch(self.source_sha256) is None
                or type(self.palette_digest) is not str
                or _SHA.fullmatch(self.palette_digest) is None):
            raise StudioSpriteAuthoringError("actual original source/palette hashes required")
        if self.quantization not in _SUPPORTED or self.source_kind not in {"png", "typed"}:
            raise StudioSpriteAuthoringError("unknown original art capture mode")

    @property
    def digest(self) -> str:
        return canonical_digest({
            "source_sha256": self.source_sha256,
            "palette_digest": self.palette_digest,
            "quantization": self.quantization,
            "source_kind": self.source_kind,
            "tiles": [list(tile) for tile in self.tiles],
        })


def _palette(colors: object) -> tuple[tuple[int, int, int, int], ...]:
    if (type(colors) is not tuple or len(colors) != 4 or
            any(type(c) is not tuple or len(c) != 4 or any(
                type(x) is not int or not 0 <= x <= 255 for x in c
            ) for c in colors)):
        raise StudioSpriteAuthoringError("four exact original RGBA palette entries required")
    return colors


def palette_identity(colors: tuple[tuple[int, int, int, int], ...]) -> str:
    return canonical_digest([list(c) for c in _palette(colors)])


def typed_artist_tiles(
    value: object, *, palette: tuple[tuple[int, int, int, int], ...],
    authorized: bool,
) -> ArtistSpriteAtlas:
    """Take concrete original pixel data from a reviewed Jeeves art edit."""
    if authorized is not True:
        raise PermissionError("designer must authorize exact sprite pixel authoring")
    colors = _palette(palette)
    if (type(value) is not list or len(value) != 6 or
            any(type(tile) is not list or len(tile) != 64 or
                any(type(p) is not int or not 0 <= p <= 3 for p in tile) for tile in value)):
        raise StudioSpriteAuthoringError("six 64-index sprite arrays must be concrete pixels")
    raw = tuple(tuple(tile) for tile in value)
    return ArtistSpriteAtlas(
        raw, canonical_digest(value), palette_identity(colors),
        "exact", "typed",
    )


def import_artist_sprite_png(
    source: bytes, *, expected_sha256: str,
    palette: tuple[tuple[int, int, int, int], ...],
    quantization: str, authorized: bool,
) -> ArtistSpriteAtlas:
    """Decode PNG bytes, quantize into actual GB/NES palette indices.

    An alpha-0 pixel maps to background index 0. Partial alpha is refused,
    preventing silent compositing mismatches between consoles and engines.
    The complete canonical input is hashed before decoding.
    """
    if authorized is not True:
        raise PermissionError("artist PNG ingest requires operator approval")
    if type(source) is not bytes or not 1 <= len(source) <= 1024 * 1024:
        raise StudioSpriteAuthoringError("original PNG bytes must be bounded")
    if (type(expected_sha256) is not str or _SHA.fullmatch(expected_sha256) is None
            or sha256(source).hexdigest() != expected_sha256):
        raise StudioSpriteAuthoringError("artist PNG differs from expected immutable content")
    if quantization not in _SUPPORTED:
        raise StudioSpriteAuthoringError("unsupported original art color quantization")
    colors = _palette(palette)
    width, height, rgba = decode_png(source)
    if (width, height) != (48, 8):
        raise StudioSpriteAuthoringError("native engine currently requires six horizontal 8x8 sprites")
    tiles = []
    for tile_index in range(6):
        pixels = []
        for y in range(8):
            for x in range(8):
                offset = (y * width + tile_index * 8 + x) * 4
                red, green, blue, alpha = rgba[offset:offset + 4]
                if alpha == 0:
                    pixels.append(0)
                    continue
                if alpha != 255:
                    raise StudioSpriteAuthoringError("partial-alpha PNG pixel cannot map to 2bpp")
                if quantization == "exact":
                    matches = [i for i, p in enumerate(colors)
                               if p[:3] == (red, green, blue)]
                    if not matches:
                        raise StudioSpriteAuthoringError("exact palette mode rejects unmapped colors")
                    pixels.append(matches[0])
                    continue
                adjustment = _BAYER[y % 4][x % 4] * 3 if quantization == "ordered4" else 0
                channels = tuple(max(0, min(255, val + adjustment))
                                 for val in (red, green, blue))
                distances = [
                    sum((channels[i] - shade[i]) ** 2 for i in range(3))
                    for shade in colors
                ]
                pixels.append(distances.index(min(distances)))
        tiles.append(tuple(pixels))
    return ArtistSpriteAtlas(
        tuple(tiles), expected_sha256, palette_identity(colors),
        quantization, "png",
    )


__all__ = [
    "ArtistSpriteAtlas", "StudioSpriteAuthoringError",
    "palette_identity", "typed_artist_tiles", "import_artist_sprite_png",
]
