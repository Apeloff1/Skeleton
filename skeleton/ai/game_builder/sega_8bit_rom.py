"""Strict Master System / Game Gear cartridge structural acceptance.

This verifies ROM shape, machine routing and mandatory header checksum. It is
not an emulator or physical-hardware gameplay attestation.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re

from .native_release_intake import _read_bounded, NativeIntakeError

_HEADER_AT = 0x7FF0
_LENGTH = 32 * 1024
_REGIONS = {"sega_master_system": 0x4, "sega_game_gear": 0x7}
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class Sega8BitROMError(ValueError):
    """Native 32KB Z80 cartridge image is malformed, incompatible or altered."""


def validate_rom(
    image: bytes, target: str, *, expected_sha256: str | None = None,
) -> dict[str, object]:
    """Bound and validate genuine cartridge *structure* without claiming play."""
    if target not in _REGIONS:
        raise Sega8BitROMError("unsupported cartridge target")
    if not isinstance(image,bytes) or len(image)!=_LENGTH:
        raise Sega8BitROMError("native cartridge must contain exactly 32KB")
    if expected_sha256 is not None:
        if not isinstance(expected_sha256,str) or not _SHA.fullmatch(expected_sha256):
            raise Sega8BitROMError("invalid expected binary digest")
        if sha256(image).hexdigest()!=expected_sha256:
            raise Sega8BitROMError("actual ROM bytes differ from expected digest")
    header=image[_HEADER_AT:_HEADER_AT+16]
    if header[:8]!=b"TMR SEGA":
        raise Sega8BitROMError("missing console boot compatibility header")
    if (header[15]>>4)!=_REGIONS[target] or (header[15]&0x0F)!=0xC:
        raise Sega8BitROMError("wrong machine region or 32KB cartridge size code")
    stored=int.from_bytes(header[10:12],"little")
    actual=sum(image[:_HEADER_AT])&0xFFFF
    if stored!=actual:
        raise Sega8BitROMError("native cartridge boot checksum mismatch")
    if not any(image[:_HEADER_AT]) or all(value==0xFF for value in image[:_HEADER_AT]):
        raise Sega8BitROMError("cartridge contains no executable payload")
    return {
        "schema":"skeleton.game_builder.sega_8bit_cartridge_structure.v1",
        "target":target,
        "bytes":len(image),
        "sha256":sha256(image).hexdigest(),
        "header_offset":_HEADER_AT,
        "header_magic_verified":True,
        "correct_machine_region_verified":True,
        "rom_size_code_verified":True,
        "native_rom_checksum_verified":True,
        "native_gameplay_executed":False,
        "emulator_playthrough_verified":False,
        "physical_hardware_verified":False,
        "release_approved":False,
        "distribution_licensed":False,
    }


def validate_rom_file(
    path: str | Path, target: str, *, expected_sha256: str | None = None,
) -> dict[str,object]:
    # Opening with Path.is_file()/read_bytes() allows symlink swaps after
    # inspection. The bounded native intake opens every ancestor and final
    # inode with no-follow descriptors; it also rejects hardlinks and pipes.
    try:
        data = _read_bounded(Path(path), max_bytes=_LENGTH)
    except (NativeIntakeError, OSError, ValueError) as exc:
        raise Sega8BitROMError(
            "ROM must be an ordinary unlinked, bounded, regular native cartridge file"
        ) from exc
    return validate_rom(data, target, expected_sha256=expected_sha256)
