"""Check actual compiled NES CHR-ROM against the studio's original tile pixels.

An iNES file can have a correct header and still contain the wrong graphics.
This qualifier reads real CHR bytes from the compiled cartridge and requires
them to match the exact source-generated NES 2bpp artwork.
It never treats a screenshot or written descriptor as native graphics proof.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .contracts import canonical_digest
from .studio_build_qualification import _header, _regular

SCHEMA = "skeleton.game_builder.nes_rom_chr_parity.v1"


class NESCHRIntegrityError(ValueError):
    """The actual cartridge pixel banks diverge from original asset source."""


def inspect_compiled_nes_chr(
    rom: bytes, source_project: str | Path,
) -> dict:
    if type(rom) is not bytes:
        raise NESCHRIntegrityError("actual original NROM bytes are required")
    try:
        _header("nes", rom)
        tiles = _regular(Path(source_project) / "assets/tiles/runtime.bin", 1024)
    except (ValueError, OSError) as exc:
        raise NESCHRIntegrityError("original cartridge or native art evidence is invalid") from exc
    if len(tiles) != 96:
        raise NESCHRIntegrityError("original NES six-tile 2bpp sprite atlas must be 96 bytes")
    if rom[5] != 1:
        raise NESCHRIntegrityError("current NES engine uses exactly one CHR ROM bank")
    start = 16 + rom[4] * 16_384
    if start + 8192 != len(rom):
        raise NESCHRIntegrityError("NES CHR bank offset is inconsistent with iNES header")
    actual = rom[start:start + len(tiles)]
    if actual != tiles:
        raise NESCHRIntegrityError("compiled cartridge CHR pixels differ from generated NES art")
    evidence = {
        "schema": SCHEMA,
        "original_nes_rom_sha256": sha256(rom).hexdigest(),
        "chr_source_sha256": sha256(tiles).hexdigest(),
        "compiled_chr_six_tiles_sha256": sha256(actual).hexdigest(),
        "matched_semantic_tiles": 6,
        "matched_indexed_pixels": 6 * 64,
        "ppu_runtime_pixels_verified": False,
        "physical_cartridge_verified": False,
        "release_authorized": False,
    }
    return {**evidence, "evidence_digest": canonical_digest(evidence)}


__all__ = ["NESCHRIntegrityError", "inspect_compiled_nes_chr"]
