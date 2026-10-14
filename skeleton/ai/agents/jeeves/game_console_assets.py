"""Bounded original-authoring codecs for console tiles, palettes and TIM images.

These codecs describe bytes. They do not load commercial ROMs, certify a
hardware port, execute source, or grant rights to imported artwork.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

ASSET_SCHEMA = "skeleton.console_asset.v1"
MAX_ASSET_BYTES = 1024 * 1024
MAX_TILES = 2048
MAX_PIXELS = 1024 * 1024


class ConsoleAssetError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TileCodec(str, Enum):
    NES_2BPP = "nes_2bpp"
    GB_2BPP = "gb_2bpp"
    SNES_4BPP = "snes_4bpp"
    GENESIS_4BPP = "genesis_4bpp"
    GBA_4BPP = "gba_4bpp"
    GBA_8BPP = "gba_8bpp"
    SMS_4BPP = "sms_4bpp"
    INDEXED_8BPP = "indexed_8bpp"


_CODEC_BITS = {
    codec: (
        2
        if codec in {TileCodec.NES_2BPP, TileCodec.GB_2BPP}
        else 8 if codec in {TileCodec.GBA_8BPP, TileCodec.INDEXED_8BPP} else 4
    )
    for codec in TileCodec
}


# Conventional RP2C02 preview RGB values. Encoded bytes remain true6bit
# NES palette indices; actual composite output varies by hardware/display.
_NES_RGB = tuple(
    tuple((word >> shift) & 255 for shift in (16, 8, 0))
    for word in (
        0x7C7C7C,
        0x0000FC,
        0x0000BC,
        0x4428BC,
        0x940084,
        0xA80020,
        0xA81000,
        0x881400,
        0x503000,
        0x007800,
        0x006800,
        0x005800,
        0x004058,
        0x000000,
        0x000000,
        0x000000,
        0xBCBCBC,
        0x0078F8,
        0x0058F8,
        0x6844FC,
        0xD800CC,
        0xE40058,
        0xF83800,
        0xE45C10,
        0xAC7C00,
        0x00B800,
        0x00A800,
        0x00A844,
        0x008888,
        0x000000,
        0x000000,
        0x000000,
        0xF8F8F8,
        0x3CBCFC,
        0x6888FC,
        0x9878F8,
        0xF878F8,
        0xF85898,
        0xF87858,
        0xFCA044,
        0xF8B800,
        0xB8F818,
        0x58D854,
        0x58F898,
        0x00E8D8,
        0x787878,
        0x000000,
        0x000000,
        0xFCFCFC,
        0xA4E4FC,
        0xB8B8F8,
        0xD8B8F8,
        0xF8B8F8,
        0xF8A4C0,
        0xF0D0B0,
        0xFCE0A8,
        0xF8D878,
        0xD8F878,
        0xB8F8B8,
        0xB8F8D8,
        0x00FCFC,
        0xF8D8F8,
        0x000000,
        0x000000,
    )
)


def _int(value: object, lower: int, upper: int, label: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ConsoleAssetError("asset_bounds", f"{label} must be within [{lower}, {upper}]")
    return value


def _sequence(value: object, maximum: int, label: str) -> Sequence:
    if not isinstance(value, (tuple, list, bytes)) or len(value) > maximum:
        raise ConsoleAssetError("asset_bounds", f"{label} must be a bounded sequence")
    return value


def _bytes(value: object, maximum: int = MAX_ASSET_BYTES) -> bytes:
    if not isinstance(value, bytes) or not 1 <= len(value) <= maximum:
        raise ConsoleAssetError("asset_byte_bounds", "Asset requires bounded actual bytes")
    return value


def _codec(value: TileCodec | str) -> TileCodec:
    try:
        return TileCodec(value)
    except (ValueError, TypeError) as exc:
        raise ConsoleAssetError("asset_codec_unknown", "Unknown native tile codec") from exc


def tile_codec_descriptor(codec: TileCodec | str) -> dict[str, object]:
    codec = _codec(codec)
    bits = _CODEC_BITS[codec]
    return {
        "codec": codec.value,
        "width": 8,
        "height": 8,
        "bits_per_pixel": bits,
        "bytes_per_tile": 8 * bits,
        "colors_per_tile": 1 << bits,
        "max_tiles": MAX_TILES,
    }


def decode_tiles(data: bytes, codec: TileCodec | str) -> tuple[tuple[int, ...], ...]:
    data, codec = _bytes(data), _codec(codec)
    size = 8 * _CODEC_BITS[codec]
    if len(data) % size or len(data) // size > MAX_TILES:
        raise ConsoleAssetError("asset_tile_shape", "Tile bytes must contain whole bounded 8x8 tiles")
    result = []
    for offset in range(0, len(data), size):
        raw = data[offset : offset + size]
        pixels = []
        for y in range(8):
            for x in range(8):
                if codec in {TileCodec.GBA_8BPP, TileCodec.INDEXED_8BPP}:
                    value = raw[y * 8 + x]
                elif codec in {TileCodec.GENESIS_4BPP, TileCodec.GBA_4BPP}:
                    byte = raw[y * 4 + x // 2]
                    shift = 4 * ((1 - x % 2) if codec == TileCodec.GENESIS_4BPP else x % 2)
                    value = byte >> shift & 15
                else:
                    value = 0
                    for plane in range(_CODEC_BITS[codec]):
                        if codec == TileCodec.NES_2BPP:
                            index = plane * 8 + y
                        elif codec == TileCodec.GB_2BPP:
                            index = y * 2 + plane
                        elif codec == TileCodec.SNES_4BPP:
                            index = (plane // 2) * 16 + y * 2 + plane % 2
                        else:
                            index = y * 4 + plane
                        value |= ((raw[index] >> (7 - x)) & 1) << plane
                pixels.append(value)
        result.append(tuple(pixels))
    return tuple(result)


def encode_tiles(tiles: Sequence[Sequence[int]], codec: TileCodec | str) -> bytes:
    codec = _codec(codec)
    tiles = _sequence(tiles, MAX_TILES, "tiles")
    if not tiles:
        raise ConsoleAssetError("asset_tile_shape", "At least one tile is required")
    bits, result = _CODEC_BITS[codec], bytearray()
    for tile in tiles:
        tile = _sequence(tile, 64, "tile pixels")
        if len(tile) != 64:
            raise ConsoleAssetError("asset_tile_shape", "Native tiles require exactly 64 pixels")
        values = [_int(value, 0, (1 << bits) - 1, "tile palette index") for value in tile]
        raw = bytearray(bits * 8)
        for y in range(8):
            for x in range(8):
                value = values[y * 8 + x]
                if codec in {TileCodec.GBA_8BPP, TileCodec.INDEXED_8BPP}:
                    raw[y * 8 + x] = value
                elif codec in {TileCodec.GENESIS_4BPP, TileCodec.GBA_4BPP}:
                    shift = 4 * ((1 - x % 2) if codec == TileCodec.GENESIS_4BPP else x % 2)
                    raw[y * 4 + x // 2] |= value << shift
                else:
                    for plane in range(bits):
                        index = (
                            plane * 8 + y
                            if codec == TileCodec.NES_2BPP
                            else (
                                y * 2 + plane
                                if codec == TileCodec.GB_2BPP
                                else (
                                    (plane // 2) * 16 + y * 2 + plane % 2
                                    if codec == TileCodec.SNES_4BPP
                                    else y * 4 + plane
                                )
                            )
                        )
                        raw[index] |= ((value >> plane) & 1) << (7 - x)
        result.extend(raw)
    return bytes(result)


def _rgba(value: object) -> tuple[int, int, int, int]:
    if isinstance(value, str):
        if (
            len(value) not in (7, 9)
            or not value.startswith("#")
            or any(char not in "0123456789abcdefABCDEF" for char in value[1:])
        ):
            raise ConsoleAssetError("asset_palette_invalid", "Colors require #rrggbb or #rrggbbaa")
        try:
            color = tuple(bytes.fromhex(value[1:]))
        except ValueError as exc:
            raise ConsoleAssetError("asset_palette_invalid", "Palette color is not hexadecimal") from exc
        return (*color, 255) if len(color) == 3 else color
    value = _sequence(value, 4, "RGBA color")
    if len(value) not in (3, 4):
        raise ConsoleAssetError("asset_palette_invalid", "Colors require three or four channels")
    color = tuple(_int(channel, 0, 255, "color channel") for channel in value)
    return (*color, 255) if len(color) == 3 else color


def color_hex(value: object) -> str:
    return "#" + bytes(_rgba(value)).hex()


def encode_palette(colors: Sequence[object], format: str) -> bytes:
    colors = _sequence(colors, 256, "palette colors")
    if not colors:
        raise ConsoleAssetError("asset_palette_invalid", "Palette is empty")
    result = bytearray()
    for color in colors:
        red, green, blue, alpha = _rgba(color)
        if format == "rgba8888":
            result.extend((red, green, blue, alpha))
        elif format in {"snes_bgr555", "gb_bgr555", "gba_bgr555", "ps1_bgr555"}:
            word = red >> 3 | (green >> 3) << 5 | (blue >> 3) << 10
            if format == "ps1_bgr555":
                if alpha == 0:
                    word = 0
                elif alpha == 128:
                    word |= 0x8000
                elif alpha != 255:
                    raise ConsoleAssetError(
                        "asset_palette_alpha",
                        "TIM alpha convention is 0,128,255; STP is drawing-mode dependent",
                    )
            elif alpha != 255:
                raise ConsoleAssetError("asset_palette_alpha", "This hardware palette has no alpha channel")
            result.extend(struct.pack("<H", word))
        elif format == "nes_palette_indices":
            if alpha != 255:
                raise ConsoleAssetError("asset_palette_alpha", "NES palette has no alpha channel")
            result.append(
                min(
                    range(64),
                    key=lambda index: sum(
                        (value - expected) ** 2
                        for value, expected in zip((red, green, blue), _NES_RGB[index], strict=True)
                    ),
                )
            )
        elif format == "gg_bgr444":
            if alpha != 255:
                raise ConsoleAssetError("asset_palette_alpha", "Game Gear palette has no alpha channel")
            result.extend(struct.pack("<H", red >> 4 | (green >> 4) << 4 | (blue >> 4) << 8))
        elif format == "genesis_bgr333":
            if alpha != 255:
                raise ConsoleAssetError("asset_palette_alpha", "Genesis palette has no alpha channel")
            result.extend(struct.pack(">H", (red >> 5) << 1 | (green >> 5) << 5 | (blue >> 5) << 9))
        elif format == "sms_rgb222":
            result.append(red >> 6 | (green >> 6) << 2 | (blue >> 6) << 4)
        elif format == "dmg_gray":
            if red != green or green != blue or red not in (0, 85, 170, 255) or alpha != 255:
                raise ConsoleAssetError(
                    "asset_palette_quantization", "DMG authoring shades require 0,85,170,255 gray"
                )
            result.append((255 - red) // 85)
        else:
            raise ConsoleAssetError("asset_palette_format", "Palette format is unsupported")
    return bytes(result)


def decode_palette(data: bytes, format: str) -> tuple[tuple[int, int, int, int], ...]:
    data = _bytes(data, 1024)
    stride = (
        4 if format == "rgba8888" else 1 if format in {"dmg_gray", "sms_rgb222", "nes_palette_indices"} else 2
    )
    if len(data) % stride or len(data) // stride > 256:
        raise ConsoleAssetError("asset_palette_invalid", "Palette byte count differs")
    result = []
    for offset in range(0, len(data), stride):
        if format == "rgba8888":
            color = tuple(data[offset : offset + 4])
        elif format in {"snes_bgr555", "gb_bgr555", "gba_bgr555", "ps1_bgr555"}:
            word = struct.unpack_from("<H", data, offset)[0]
            values = (word & 31, word >> 5 & 31, word >> 10 & 31)
            alpha = (
                0
                if word == 0 and format == "ps1_bgr555"
                else 128 if word & 0x8000 and format == "ps1_bgr555" else 255
            )
            color = (*((value << 3) | (value >> 2) for value in values), alpha)
        elif format == "nes_palette_indices":
            index = data[offset]
            if index > 63:
                raise ConsoleAssetError("asset_palette_invalid", "NES palette index exceeds6bit range")
            color = (*_NES_RGB[index], 255)
        elif format == "gg_bgr444":
            word = struct.unpack_from("<H", data, offset)[0]
            if word & 0xF000:
                raise ConsoleAssetError("asset_palette_invalid", "Game Gear palette reservedbits are set")
            color = (*(((word >> shift) & 15) * 17 for shift in (0, 4, 8)), 255)
        elif format == "genesis_bgr333":
            word = struct.unpack_from(">H", data, offset)[0]
            if word & ~0x0EEE:
                raise ConsoleAssetError("asset_palette_invalid", "Genesis palette reserved bits are set")
            color = (*(round(((word >> shift) & 7) * 255 / 7) for shift in (1, 5, 9)), 255)
        elif format == "sms_rgb222":
            word = data[offset]
            if word > 63:
                raise ConsoleAssetError("asset_palette_invalid", "SMS palette reserved bits are set")
            color = (*(((word >> shift) & 3) * 85 for shift in (0, 2, 4)), 255)
        elif format == "dmg_gray":
            word = data[offset]
            if word > 3:
                raise ConsoleAssetError("asset_palette_invalid", "DMG shade exceeds hardware range")
            color = (255 - word * 85,) * 3 + (255,)
        else:
            raise ConsoleAssetError("asset_palette_format", "Palette format is unsupported")
        result.append(color)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class IndexedImage:
    width: int
    height: int
    pixels: bytes
    palette: tuple[tuple[int, int, int, int], ...]

    def __post_init__(self) -> None:
        _int(self.width, 1, 2048, "image width")
        _int(self.height, 1, 2048, "image height")
        if (
            self.width * self.height > MAX_PIXELS
            or not isinstance(self.pixels, bytes)
            or len(self.pixels) != self.width * self.height
        ):
            raise ConsoleAssetError("asset_image_shape", "Indexed image dimensions and bytes differ")
        palette = tuple(_rgba(value) for value in _sequence(self.palette, 256, "image palette"))
        if not palette or max(self.pixels) >= len(palette):
            raise ConsoleAssetError("asset_image_palette", "Image pixels reference an absent color")
        object.__setattr__(self, "palette", palette)

    def rgba_bytes(self) -> bytes:
        return b"".join(bytes(self.palette[value]) for value in self.pixels)

    def as_dict(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "pixels_base64": base64.b64encode(self.pixels).decode(),
            "palette": [color_hex(value) for value in self.palette],
            "pixel_digest": hashlib.sha256(self.pixels).hexdigest(),
        }

    def transform(
        self, *, flip_x: bool = False, flip_y: bool = False, quarter_turns: int = 0
    ) -> IndexedImage:
        if type(flip_x) is not bool or type(flip_y) is not bool:
            raise ConsoleAssetError("asset_transform_invalid", "Image flips must be booleans")
        turns = _int(quarter_turns, 0, 3, "quarter turns")
        width, height, pixels = self.width, self.height, self.pixels
        if flip_x:
            pixels = bytes(pixels[y * width + width - 1 - x] for y in range(height) for x in range(width))
        if flip_y:
            pixels = b"".join(pixels[y * width : (y + 1) * width] for y in reversed(range(height)))
        for _ in range(turns):
            pixels = bytes(pixels[(height - 1 - x) * width + y] for y in range(width) for x in range(height))
            width, height = height, width
        return IndexedImage(width, height, pixels, self.palette)


def png_rgba(pixels: bytes, width: int, height: int) -> bytes:
    _int(width, 1, 2048, "PNG width")
    _int(height, 1, 2048, "PNG height")
    if width * height > MAX_PIXELS or not isinstance(pixels, bytes) or len(pixels) != width * height * 4:
        raise ConsoleAssetError("asset_image_shape", "Actual RGBA bytes differ from dimensions")

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = b"".join(b"\0" + pixels[y * width * 4 : (y + 1) * width * 4] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )


@dataclass(frozen=True, slots=True)
class TIMImage:
    """Exact PS1 TIM planes; STP is preserved as raw palette/pixel words."""

    bits_per_pixel: int
    width: int
    height: int
    pixels: bytes
    palette_words: tuple[int, ...] = ()
    palette_width: int = 0
    palette_height: int = 0
    image_x: int = 0
    image_y: int = 0
    palette_x: int = 0
    palette_y: int = 0

    def __post_init__(self) -> None:
        if self.bits_per_pixel not in (4, 8, 16, 24):
            raise ConsoleAssetError("asset_tim_mode", "TIM bit depth is unsupported")
        _int(self.width, 1, 2048, "TIM width")
        _int(self.height, 1, 512, "TIM height")
        if self.width * self.height > MAX_PIXELS:
            raise ConsoleAssetError("asset_tim_bounds", "TIM pixel capacity exceeded")
        stride = ((self.width * self.bits_per_pixel + 15) // 16) * 2
        if (
            self.bits_per_pixel != 24
            and self.width * self.bits_per_pixel % 16
            or not isinstance(self.pixels, bytes)
            or len(self.pixels) != stride * self.height
        ):
            raise ConsoleAssetError("asset_tim_shape", "TIM rows must align to 16-bit VRAM words")
        row_words = stride // 2
        if self.image_x + row_words > 1024 or self.image_y + self.height > 512:
            raise ConsoleAssetError("asset_tim_vram", "TIM image exceeds PS1 VRAM geometry")
        for value in (self.image_x, self.image_y, self.palette_x, self.palette_y):
            _int(value, 0, 1023, "TIM VRAM origin")
        _int(self.palette_width, 0, 1024, "TIM CLUT width")
        _int(self.palette_height, 0, 512, "TIM CLUT height")
        palette = tuple(
            _int(value, 0, 65535, "TIM CLUT word")
            for value in _sequence(self.palette_words, 4096, "TIM CLUT")
        )
        if self.bits_per_pixel in (4, 8):
            minimum = 1 << self.bits_per_pixel
            if (
                self.palette_width < minimum
                or self.palette_width % minimum
                or self.palette_x % 16
                or self.palette_width * self.palette_height != len(palette)
                or self.palette_height < 1
                or len(palette) % minimum
                or self.palette_x + self.palette_width > 1024
                or self.palette_y + self.palette_height > 512
            ):
                raise ConsoleAssetError(
                    "asset_tim_palette", "Indexed TIM requires complete bounded CLUT rows"
                )
        elif palette or self.palette_width or self.palette_height:
            raise ConsoleAssetError("asset_tim_palette", "Direct-color TIM has no CLUT")
        object.__setattr__(self, "palette_words", palette)

    def indexed(self, palette_index: int = 0) -> IndexedImage:
        if self.bits_per_pixel not in (4, 8):
            raise ConsoleAssetError("asset_tim_mode", "Only indexed TIM exposes palette indices")
        count = 1 << self.bits_per_pixel
        _int(palette_index, 0, len(self.palette_words) // count - 1, "TIM palette index")
        palette = decode_palette(
            b"".join(
                struct.pack("<H", word)
                for word in self.palette_words[palette_index * count : (palette_index + 1) * count]
            ),
            "ps1_bgr555",
        )
        pixels = (
            self.pixels
            if self.bits_per_pixel == 8
            else bytes(value >> (4 * (index % 2)) & 15 for value in self.pixels for index in (0, 1))
        )
        return IndexedImage(self.width, self.height, pixels, palette)

    def rgba_bytes(self, palette_index: int = 0) -> bytes:
        if self.bits_per_pixel in (4, 8):
            return self.indexed(palette_index).rgba_bytes()
        if self.bits_per_pixel == 16:
            palette = [
                decode_palette(self.pixels[index : index + 2], "ps1_bgr555")[0]
                for index in range(0, len(self.pixels), 2)
            ]
            return b"".join(bytes(color) for color in palette)
        stride = ((self.width * 24 + 15) // 16) * 2
        return b"".join(
            self.pixels[y * stride + x * 3 : y * stride + x * 3 + 3] + b"\xff"
            for y in range(self.height)
            for x in range(self.width)
        )


def decode_tim(data: bytes) -> TIMImage:
    data = _bytes(data)
    if len(data) < 20 or struct.unpack_from("<I", data)[0] != 0x10:
        raise ConsoleAssetError("asset_tim_header", "TIM magic or length differs")
    flags = struct.unpack_from("<I", data, 4)[0]
    if flags & ~0x0B or flags & 3 not in (0, 1, 2, 3):
        raise ConsoleAssetError("asset_tim_flags", "TIM flags are invalid")
    mode, has_palette = flags & 3, bool(flags & 8)
    if has_palette != (mode in (0, 1)):
        raise ConsoleAssetError("asset_tim_palette", "TIM indexed mode and CLUT presence differ")
    offset, palette, px, py, pw, ph = 8, (), 0, 0, 0, 0

    def block(position: int) -> tuple[int, int, int, int, bytes, int]:
        if position + 12 > len(data):
            raise ConsoleAssetError("asset_tim_truncated", "TIM block header is truncated")
        length, x, y, width, height = struct.unpack_from("<IHHHH", data, position)
        if length < 12 or position + length > len(data) or width == 0 or height == 0:
            raise ConsoleAssetError("asset_tim_truncated", "TIM block extent is invalid")
        return x, y, width, height, data[position + 12 : position + length], position + length

    if has_palette:
        px, py, pw, ph, raw, offset = block(offset)
        if len(raw) != pw * ph * 2 or pw * ph > 4096:
            raise ConsoleAssetError("asset_tim_palette", "TIM CLUT size differs")
        palette = tuple(value[0] for value in struct.iter_unpack("<H", raw))
    ix, iy, words, height, pixels, offset = block(offset)
    if offset != len(data) or len(pixels) != words * height * 2:
        raise ConsoleAssetError("asset_tim_trailing", "TIM image or trailing bytes differ")
    bits = (4, 8, 16, 24)[mode]
    if bits != 24 and words * 16 % bits:
        raise ConsoleAssetError("asset_tim_shape", "TIM word width cannot represent whole pixels")
    return TIMImage(bits, words * 16 // bits, height, pixels, palette, pw, ph, ix, iy, px, py)


def encode_tim(image: TIMImage) -> bytes:
    if not isinstance(image, TIMImage):
        raise ConsoleAssetError("asset_tim_invalid", "Validated TIM image is required")
    image = TIMImage(**{field: getattr(image, field) for field in image.__dataclass_fields__})
    mode = (4, 8, 16, 24).index(image.bits_per_pixel)
    result = bytearray(struct.pack("<II", 0x10, mode | (8 if mode < 2 else 0)))

    def block(x: int, y: int, width: int, height: int, payload: bytes) -> bytes:
        return struct.pack("<IHHHH", len(payload) + 12, x, y, width, height) + payload

    if mode < 2:
        result.extend(
            block(
                image.palette_x,
                image.palette_y,
                image.palette_width,
                image.palette_height,
                b"".join(struct.pack("<H", value) for value in image.palette_words),
            )
        )
    result.extend(
        block(
            image.image_x,
            image.image_y,
            (image.width * image.bits_per_pixel + 15) // 16,
            image.height,
            image.pixels,
        )
    )
    return _bytes(bytes(result))


def tilemap_entry(
    *,
    target: str,
    tile: int,
    palette: int = 0,
    flip_x: bool = False,
    flip_y: bool = False,
    priority: bool = False,
    bank: int = 0,
) -> bytes:
    if any(type(value) is not bool for value in (flip_x, flip_y, priority)):
        raise ConsoleAssetError("asset_tilemap_invalid", "Tilemap flag type differs")
    if target == "nes":
        if palette or flip_x or flip_y or priority or bank:
            raise ConsoleAssetError(
                "asset_tilemap_attribute", "NES name table attributes are a separate 2x2-tile palette plane"
            )
        return bytes([_int(tile, 0, 255, "NES tile")])
    if target in {"game_boy", "game_boy_color"}:
        tile = _int(tile, 0, 255, "GB tile")
        if target == "game_boy":
            if palette or flip_x or flip_y or priority or bank:
                raise ConsoleAssetError("asset_tilemap_attribute", "DMG map has no CGB attribute plane")
            return bytes([tile])
        attr = (
            _int(palette, 0, 7, "CGB palette")
            | _int(bank, 0, 1, "CGB bank") << 3
            | flip_x << 5
            | flip_y << 6
            | priority << 7
        )
        return bytes([tile, attr])
    if target in {"snes", "game_boy_advance", "genesis", "master_system"}:
        limits = {
            "snes": (1023, 7),
            "game_boy_advance": (1023, 15),
            "genesis": (2047, 3),
            "master_system": (511, 1),
        }
        upper, palettes = limits[target]
        tile = _int(tile, 0, upper, "native tile index")
        palette = _int(palette, 0, palettes, "tile palette")
        if bank:
            raise ConsoleAssetError("asset_tilemap_attribute", "This entry has no independent bank selector")
        if target == "snes":
            word = tile | palette << 10 | priority << 13 | flip_x << 14 | flip_y << 15
        elif target == "game_boy_advance":
            if priority:
                raise ConsoleAssetError(
                    "asset_tilemap_attribute", "GBA text map priority belongs to the layer"
                )
            word = tile | flip_x << 10 | flip_y << 11 | palette << 12
        elif target == "genesis":
            word = tile | flip_x << 11 | flip_y << 12 | palette << 13 | priority << 15
        else:
            word = tile | flip_x << 9 | flip_y << 10 | palette << 11 | priority << 12
        return struct.pack(">H" if target == "genesis" else "<H", word)
    raise ConsoleAssetError("asset_tilemap_target", "Target has no declared native tilemap entry codec")


def nes_attribute_table(palettes: Sequence[int], width: int, height: int) -> bytes:
    _int(width, 1, 32, "NES name table width")
    _int(height, 1, 30, "NES name table height")
    palettes = _sequence(palettes, 960, "NES palette plane")
    if len(palettes) != width * height:
        raise ConsoleAssetError("asset_tilemap_shape", "NES palette plane dimensions differ")
    values = [_int(value, 0, 3, "NES palette index") for value in palettes]
    result = bytearray(64)
    for y in range(height):
        for x in range(width):
            index = y * width + x
            # Hardware palettes apply to a 2x2 tile quadrant, not each tile.
            for other_y in range(y & ~1, min((y & ~1) + 2, height)):
                for other_x in range(x & ~1, min((x & ~1) + 2, width)):
                    if values[other_y * width + other_x] != values[index]:
                        raise ConsoleAssetError(
                            "asset_tilemap_attribute", "NES quadrant uses conflicting palette indices"
                        )
            attr = (y // 4) * 8 + x // 4
            shift = ((y % 4) // 2) * 4 + ((x % 4) // 2) * 2
            result[attr] |= values[index] << shift
    return bytes(result)


def asset_receipt(
    data: bytes,
    *,
    asset_id: str,
    kind: str,
    codec: str,
    author_ref: str,
    source_digest: str | None = None,
    transformations: Sequence[str] = (),
) -> dict[str, object]:
    data = _bytes(data)
    if (
        not isinstance(asset_id, str)
        or not 1 <= len(asset_id) <= 96
        or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
            for char in asset_id
        )
    ):
        raise ConsoleAssetError("asset_identity", "Asset ID is invalid")
    if (
        not isinstance(author_ref, str)
        or not 1 <= len(author_ref) <= 256
        or any(ord(char) < 32 for char in author_ref)
    ):
        raise ConsoleAssetError("asset_provenance", "Explicit original author reference is required")
    if kind not in {"tiles", "image", "palette", "audio", "data"}:
        raise ConsoleAssetError("asset_kind", "Asset kind is unknown")
    transforms = _sequence(transformations, 64, "asset transformations")
    if any(not isinstance(value, str) or not 1 <= len(value) <= 128 for value in transforms):
        raise ConsoleAssetError("asset_provenance", "Transformation refs exceed bounds")
    if source_digest is not None and (
        not isinstance(source_digest, str)
        or len(source_digest) != 64
        or any(char not in "0123456789abcdef" for char in source_digest)
    ):
        raise ConsoleAssetError("asset_provenance", "Source SHA256 differs")
    return {
        "schema_version": ASSET_SCHEMA,
        "asset_id": asset_id,
        "kind": kind,
        "codec": codec,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "data_base64": base64.b64encode(data).decode(),
        "provenance": {
            "kind": "original_authoring",
            "author_ref": author_ref,
            "source_digest": source_digest or hashlib.sha256(data).hexdigest(),
            "transformations": list(transforms),
        },
        "rights_verified": False,
    }


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Decode actual bounded noninterlaced8bit PNG to RGBA, checking CRC/extent."""
    data = _bytes(data)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ConsoleAssetError("asset_png_header", "PNG signature differs")
    cursor, width, height, color_type, channels = 8, 0, 0, -1, 0
    palette, alpha, compressed = None, b"", bytearray()
    seen_header, seen_end, seen_data, ended_data = False, False, False, False
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise ConsoleAssetError("asset_png_truncated", "PNG chunk header is truncated")
        length = struct.unpack_from(">I", data, cursor)[0]
        kind = data[cursor + 4 : cursor + 8]
        if length > MAX_ASSET_BYTES or cursor + length + 12 > len(data):
            raise ConsoleAssetError("asset_png_truncated", "PNG chunk size exceeds actual bytes")
        raw = data[cursor + 8 : cursor + 8 + length]
        crc = struct.unpack_from(">I", data, cursor + 8 + length)[0]
        if binascii.crc32(kind + raw) & 0xFFFFFFFF != crc:
            raise ConsoleAssetError("asset_png_crc", "PNG chunk checksum differs")
        if not seen_header and kind != b"IHDR":
            raise ConsoleAssetError("asset_png_header", "PNG first chunk must be IHDR")
        if kind == b"IHDR":
            if seen_header or length != 13:
                raise ConsoleAssetError("asset_png_header", "PNG IHDR repeats or has another size")
            width, height, depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", raw
            )
            _int(width, 1, 2048, "PNG width")
            _int(height, 1, 2048, "PNG height")
            if (
                width * height > MAX_PIXELS
                or depth != 8
                or color_type not in (0, 2, 3, 4, 6)
                or compression
                or filter_method
                or interlace
            ):
                raise ConsoleAssetError(
                    "asset_png_unsupported", "PNG requires bounded noninterlaced8bit supported planes"
                )
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
            seen_header = True
        elif kind == b"PLTE":
            if (
                seen_data
                or palette is not None
                or not length
                or length % 3
                or length > 768
                or color_type in (0, 4)
            ):
                raise ConsoleAssetError("asset_png_palette", "PNG palette extent/order differs")
            palette = tuple(tuple(raw[index : index + 3]) for index in range(0, length, 3))
        elif kind == b"tRNS":
            if seen_data or alpha or color_type in (4, 6):
                raise ConsoleAssetError("asset_png_alpha", "PNG transparency order/mode differs")
            if (
                color_type == 3
                and (palette is None or not length or length > len(palette))
                or color_type == 0
                and length != 2
                or color_type == 2
                and length != 6
            ):
                raise ConsoleAssetError("asset_png_alpha", "PNG transparency extent differs")
            alpha = raw
        elif kind == b"IDAT":
            if ended_data or seen_end or color_type == 3 and palette is None:
                raise ConsoleAssetError("asset_png_order", "PNG image data order differs")
            compressed.extend(raw)
            seen_data = True
        elif kind == b"IEND":
            if length or not seen_data or cursor + 12 != len(data):
                raise ConsoleAssetError("asset_png_trailing", "PNG IEND or trailing bytes differ")
            seen_end = True
        elif not kind[0] & 32:
            raise ConsoleAssetError("asset_png_unsupported", "Unknown critical PNG chunk")
        if seen_data and kind not in (b"IDAT", b"IEND"):
            ended_data = True
        cursor += length + 12
    if not seen_end:
        raise ConsoleAssetError("asset_png_truncated", "PNG has no terminal image receipt")
    stride = width * channels
    expected = (stride + 1) * height
    try:
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise ConsoleAssetError("asset_png_corrupt", "PNG compressed pixels are invalid") from exc
    if len(decoded) != expected or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise ConsoleAssetError(
            "asset_png_inflate_bounds", "PNG decoded rows differ from bounded actual geometry"
        )
    pixels = bytearray(width * height * 4)
    previous = bytearray(stride)
    gray_key = struct.unpack(">H", alpha)[0] if color_type == 0 and alpha else None
    rgb_key = struct.unpack(">HHH", alpha) if color_type == 2 and alpha else None
    for y in range(height):
        offset = y * (stride + 1)
        filter_type = decoded[offset]
        row = bytearray(decoded[offset + 1 : offset + 1 + stride])
        if filter_type > 4:
            raise ConsoleAssetError("asset_png_filter", "PNG filter type differs")
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                prediction = left + up - upper_left
                distances = (abs(prediction - left), abs(prediction - up), abs(prediction - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
            else:
                predictor = 0
            row[index] = (row[index] + predictor) & 255
        for x in range(width):
            source = x * channels
            target = (y * width + x) * 4
            if color_type == 6:
                color = row[source : source + 4]
            elif color_type == 4:
                color = bytes((row[source],) * 3 + (row[source + 1],))
            elif color_type == 0:
                color = bytes((row[source],) * 3 + (0 if row[source] == gray_key else 255,))
            elif color_type == 2:
                values = tuple(row[source : source + 3])
                color = bytes((*values, 0 if values == rgb_key else 255))
            else:
                index = row[source]
                if index >= len(palette):
                    raise ConsoleAssetError("asset_png_palette", "PNG sample references absent palette color")
                color = bytes((*palette[index], alpha[index] if index < len(alpha) else 255))
            pixels[target : target + 4] = color
        previous = row
    return width, height, bytes(pixels)


def decode_pcm_wav(data: bytes) -> dict[str, object]:
    """Measured PCM WAVE data, not metadata-only audio admission."""
    import io
    import wave

    data = _bytes(data)
    if (
        len(data) < 44
        or data[:4] != b"RIFF"
        or data[8:12] != b"WAVE"
        or struct.unpack_from("<I", data, 4)[0] + 8 != len(data)
    ):
        raise ConsoleAssetError("asset_audio_header", "WAVE RIFF extent differs")
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            channels, width, rate, frames = (
                source.getnchannels(),
                source.getsampwidth(),
                source.getframerate(),
                source.getnframes(),
            )
            if (
                source.getcomptype() != "NONE"
                or channels not in (1, 2)
                or width not in (1, 2)
                or not 8000 <= rate <= 96000
                or not 1 <= frames <= rate * 10
            ):
                raise ConsoleAssetError(
                    "asset_audio_format", "Audio requires bounded8/16bit mono/stereo PCM, up to10seconds"
                )
            pcm = source.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ConsoleAssetError("asset_audio_corrupt", "WAVE PCM is invalid") from exc
    if len(pcm) != frames * channels * width:
        raise ConsoleAssetError("asset_audio_truncated", "PCM sample bytes differ from declared frame count")
    return {
        "channels": channels,
        "sample_width": width,
        "sample_rate": rate,
        "sample_frames": frames,
        "duration_seconds": frames / rate,
        "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "pcm": pcm,
    }


def transform_rgba(
    pixels: bytes,
    width: int,
    height: int,
    *,
    flip_x: bool = False,
    flip_y: bool = False,
    quarter_turns: int = 0,
) -> tuple[int, int, bytes]:
    _int(width, 1, 2048, "RGBA width")
    _int(height, 1, 2048, "RGBA height")
    if (
        width * height > MAX_PIXELS
        or not isinstance(pixels, bytes)
        or len(pixels) != width * height * 4
        or type(flip_x) is not bool
        or type(flip_y) is not bool
    ):
        raise ConsoleAssetError(
            "asset_transform_invalid", "Actual RGBA dimensions and transform flags differ"
        )
    turns = _int(quarter_turns, 0, 3, "quarter turns")
    if flip_x:
        pixels = b"".join(
            pixels[(y * width + width - 1 - x) * 4 : (y * width + width - 1 - x) * 4 + 4]
            for y in range(height)
            for x in range(width)
        )
    if flip_y:
        pixels = b"".join(pixels[y * width * 4 : (y + 1) * width * 4] for y in reversed(range(height)))
    for _ in range(turns):
        pixels = b"".join(
            pixels[((height - 1 - x) * width + y) * 4 : ((height - 1 - x) * width + y) * 4 + 4]
            for y in range(width)
            for x in range(height)
        )
        width, height = height, width
    return width, height, pixels


def transform_tim(
    image: TIMImage, *, flip_x: bool = False, flip_y: bool = False, quarter_turns: int = 0
) -> TIMImage:
    """Transform actual TIM samples while preserving CLUT/STP/native words."""
    if not isinstance(image, TIMImage) or type(flip_x) is not bool or type(flip_y) is not bool:
        raise ConsoleAssetError(
            "asset_transform_invalid", "Validated TIM and boolean transform flags required"
        )
    turns = _int(quarter_turns, 0, 3, "quarter turns")
    width, height = image.width, image.height
    if image.bits_per_pixel in (4, 8):
        # Independent of CLUT selection; alloriginal palette words preserved.
        samples = tuple(
            bytes((value,))
            for value in (
                image.pixels
                if image.bits_per_pixel == 8
                else bytes(value >> (4 * index) & 15 for value in image.pixels for index in (0, 1))
            )
        )
    else:
        unit = image.bits_per_pixel // 8
        stride = ((image.width * image.bits_per_pixel + 15) // 16) * 2
        samples = tuple(
            image.pixels[y * stride + x * unit : y * stride + (x + 1) * unit]
            for y in range(height)
            for x in range(width)
        )
    if flip_x:
        samples = tuple(samples[y * width + width - 1 - x] for y in range(height) for x in range(width))
    if flip_y:
        samples = tuple(samples[y * width + x] for y in reversed(range(height)) for x in range(width))
    for _ in range(turns):
        samples = tuple(samples[(height - 1 - x) * width + y] for y in range(width) for x in range(height))
        width, height = height, width
    if image.bits_per_pixel != 24 and width * image.bits_per_pixel % 16:
        raise ConsoleAssetError(
            "asset_tim_alignment", "Rotated TIM row does not fit native16bit word alignment"
        )
    if image.bits_per_pixel == 4:
        values = bytes(sample[0] for sample in samples)
        pixels = bytes(values[index] | values[index + 1] << 4 for index in range(0, len(values), 2))
    elif image.bits_per_pixel == 24:
        row_bytes = width * 3
        stride = ((row_bytes + 1) // 2) * 2
        pixels = b"".join(
            b"".join(samples[y * width : (y + 1) * width]) + bytes(stride - row_bytes) for y in range(height)
        )
    else:
        pixels = b"".join(samples)
    return TIMImage(
        image.bits_per_pixel,
        width,
        height,
        pixels,
        image.palette_words,
        image.palette_width,
        image.palette_height,
        image.image_x,
        image.image_y,
        image.palette_x,
        image.palette_y,
    )


def image_to_tiles(
    pixels: bytes, width: int, height: int, colors: Sequence[object], codec: TileCodec | str
) -> tuple[tuple[tuple[int, ...], ...], dict[str, object]]:
    """Measured original RGBA-to-native quantization, without silent resizing."""
    _int(width, 1, 2048, "image width")
    _int(height, 1, 2048, "image height")
    if width * height > MAX_PIXELS or not isinstance(pixels, bytes) or len(pixels) != width * height * 4:
        raise ConsoleAssetError("asset_image_shape", "RGBA source dimensions differ")
    codec = _codec(codec)
    palette = tuple(_rgba(color) for color in _sequence(colors, 256, "palette colors"))
    if not palette or len(palette) > 1 << _CODEC_BITS[codec]:
        raise ConsoleAssetError("asset_palette_invalid", "Palette exceeds native index capacity")
    columns, rows = (width + 7) // 8, (height + 7) // 8
    if columns * rows > MAX_TILES:
        raise ConsoleAssetError(
            "asset_tile_capacity",
            "Actual image requires more than2048tiles; explicit authoring segmentation required",
        )
    cache = {}
    tiles = []
    error = 0
    transparent = 0
    for ty in range(rows):
        for tx in range(columns):
            tile = []
            for y in range(8):
                for x in range(8):
                    sx, sy = tx * 8 + x, ty * 8 + y
                    if sx >= width or sy >= height:
                        tile.append(0)
                        continue
                    at = (sy * width + sx) * 4
                    color = tuple(pixels[at : at + 4])
                    if not color[3]:
                        index = 0
                        transparent += 1
                    elif color in cache:
                        index = cache[color]
                    else:
                        index = min(
                            range(len(palette)),
                            key=lambda index: sum(
                                (color[channel] - palette[index][channel]) ** 2 for channel in range(3)
                            ),
                        )
                        cache[color] = index
                    error += sum((color[channel] - palette[index][channel]) ** 2 for channel in range(3))
                    tile.append(index)
            tiles.append(tuple(tile))
    encoded = encode_tiles(tiles, codec)
    return tuple(tiles), {
        "schema_version": "skeleton.console_image_quantization.v1",
        "source_pixel_sha256": hashlib.sha256(pixels).hexdigest(),
        "source_width": width,
        "source_height": height,
        "tile_columns": columns,
        "tile_rows": rows,
        "tile_count": len(tiles),
        "codec": codec.value,
        "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
        "mean_squared_rgb_error": error / (width * height * 3),
        "transparent_pixels": transparent,
        "alpha_strategy": "transparent source maps index0; actual sprite/background opacity requires declared native drawing-mode integration",
        "padding": "index0 outside actual source bounds",
        "resized": False,
    }
