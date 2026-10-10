"""Hardware-specific original tile bundles, with explicit unqualified provenance.

No ROM, copyrighted game content, proprietary SDK or release approval is made
by this source-data compiler. It requires an operator origin acknowledgement,
then emits auditable bytes and optional C99/RGBDS/ca65 source declarations.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .bitplanes import (
    encode_gb_2bpp, decode_gb_2bpp, encode_nes_2bpp, decode_nes_2bpp,
    encode_snes_4bpp, decode_snes_4bpp, encode_sms_4bpp, decode_sms_4bpp,
    encode_genesis_4bpp, decode_genesis_4bpp,
)

class PortableAssetError(ValueError):
    """Original tile admission, native layout, or export formatting refused."""

_CODECS = {
    "nintendo_game_boy": ("gb_2bpp", 16, encode_gb_2bpp, decode_gb_2bpp),
    "nintendo_game_boy_color": ("gb_2bpp", 16, encode_gb_2bpp, decode_gb_2bpp),
    "nintendo_famicom": ("nes_2bpp", 16, encode_nes_2bpp, decode_nes_2bpp),
    "nintendo_snes": ("snes_4bpp", 32, encode_snes_4bpp, decode_snes_4bpp),
    "sega_master_system": ("sms_4bpp", 32, encode_sms_4bpp, decode_sms_4bpp),
    "sega_game_gear": ("sms_4bpp", 32, encode_sms_4bpp, decode_sms_4bpp),
    "sega_mega_drive": ("genesis_4bpp", 32, encode_genesis_4bpp, decode_genesis_4bpp),
}

@dataclass(frozen=True, slots=True)
class PortableTileBundle:
    """A byte-accurate, source-only tile batch, not a legal or build receipt."""
    target_id: str
    tile_codec: str
    tile_count: int
    native_bytes: bytes
    native_sha256: str
    source_originality_acknowledged: bool = True
    independent_rights_cleared: bool = False
    native_binary_verified: bool = False
    release_authorized: bool = False

    def __post_init__(self) -> None:
        definition = _CODECS.get(self.target_id)
        if definition is None or self.tile_codec != definition[0]:
            raise PortableAssetError("unknown or incompatible native tile codec")
        if type(self.tile_count) is not int or not 1 <= self.tile_count <= 256:
            raise PortableAssetError("bundle tile count exceeds 256")
        if (type(self.native_bytes) is not bytes
                or len(self.native_bytes) != self.tile_count * definition[1]
                or len(self.native_bytes) > 8192):
            raise PortableAssetError("bundle native bytes do not match codec geometry")
        if self.native_sha256 != sha256(self.native_bytes).hexdigest():
            raise PortableAssetError("bundle data does not match content digest")
        if (self.source_originality_acknowledged is not True
                or self.independent_rights_cleared is not False
                or self.native_binary_verified is not False
                or self.release_authorized is not False):
            raise PortableAssetError("source compiler cannot self-certify rights or release")

def compile_original_tile_bundle(
    target_id: str, tiles: object, *, acknowledged_original_source: bool,
) -> PortableTileBundle:
    """Convert one author-acknowledged indexed tile set into real hardware bytes."""
    if acknowledged_original_source is not True:
        raise PermissionError("explicit original-source acknowledgement required")
    if type(target_id) is not str or target_id not in _CODECS:
        raise PortableAssetError("target has no implemented original tile codec")
    if not isinstance(tiles, (tuple, list)) or not 1 <= len(tiles) <= 256:
        raise PortableAssetError("one to 256 original 8x8 indexed tiles required")
    codec, _, encode, _ = _CODECS[target_id]
    native = b"".join(encode(tile) for tile in tiles)
    return PortableTileBundle(
        target_id=target_id, tile_codec=codec, tile_count=len(tiles),
        native_bytes=native, native_sha256=sha256(native).hexdigest(),
    )

def verify_original_tile_roundtrip(bundle: PortableTileBundle, tiles: object) -> bool:
    """Prove tile-byte fidelity; source rights remain independent of fidelity."""
    if not isinstance(bundle, PortableTileBundle):
        raise PortableAssetError("typed portable tile bundle required")
    if not isinstance(tiles, (tuple, list)) or len(tiles) != bundle.tile_count:
        raise PortableAssetError("original tile count mismatch")
    _, width, _, decode = _CODECS[bundle.target_id]
    recovered = tuple(decode(bundle.native_bytes[i:i+width])
                      for i in range(0, len(bundle.native_bytes), width))
    try:
        canonical = tuple(tuple(tuple(row) for row in tile) for tile in tiles)
    except (TypeError, ValueError) as exc:
        raise PortableAssetError("invalid original tile geometry") from exc
    return recovered == canonical

def emit_original_tile_source(
    bundle: PortableTileBundle, *, syntax: str, symbol: str="ORIGINAL_TILES",
) -> str:
    """Bounded native source declaration for C99, RGBDS, or ca65 assemblers."""
    if not isinstance(bundle, PortableTileBundle):
        raise PortableAssetError("typed byte-accurate bundle required")
    if not isinstance(symbol, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", symbol) is None:
        raise PortableAssetError("source symbol must be a bounded identifier")
    if syntax not in ("c99", "rgbds", "ca65"):
        raise PortableAssetError("only audited source declaration syntaxes supported")
    if syntax == "rgbds" and bundle.tile_codec != "gb_2bpp":
        raise PortableAssetError("RGBDS target needs native GB bitplane layout")
    if syntax == "ca65" and bundle.tile_codec != "nes_2bpp":
        raise PortableAssetError("ca65 target needs native NES CHR bitplane layout")
    data = bundle.native_bytes
    if syntax == "c99":
        chunks = [", ".join(f"0x{b:02x}" for b in data[i:i+16])
                  for i in range(0, len(data), 16)]
        return ("#include <stdint.h>\n"
                f"static const uint8_t {symbol}[{len(data)}] = {{\n"
                + "".join("    " + row + ("," if i < len(chunks)-1 else "")
                          + "\n" for i, row in enumerate(chunks))
                + "};\n")
    directive = "db" if syntax == "rgbds" else ".byte"
    lines = [symbol + ":"]
    for i in range(0, len(data), 8 if syntax == "rgbds" else 16):
        row = data[i:i+(8 if syntax == "rgbds" else 16)]
        lines.append("    " + directive + " " + ", ".join(f"${b:02X}" for b in row))
    return "\n".join(lines) + "\n"
