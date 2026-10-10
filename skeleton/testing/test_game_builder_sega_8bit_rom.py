"""Byte-level Sega 8-bit ROM format checks; synthetic fixtures are NOT games."""
from __future__ import annotations

from hashlib import sha256

import pytest

from skeleton.ai.game_builder.sega_8bit_rom import (
    Sega8BitROMError,validate_rom,validate_rom_file,
)


def _synthetic_header(target="sega_master_system"):
    """A synthetic header/checksum fixture, deliberately NOT executable gameplay."""
    blob=bytearray(32768)
    blob[0:4]=b"TEST"
    blob[0x7ff0:0x7ff8]=b"TMR SEGA"
    blob[0x7fff]=0x4c if target=="sega_master_system" else 0x7c
    blob[0x7ffa:0x7ffc]=(sum(blob[:0x7ff0])&0xffff).to_bytes(2,"little")
    return bytes(blob)


@pytest.mark.parametrize("target",("sega_master_system","sega_game_gear"))
def test_hardware_compatibility_header_and_independent_exact_digest(target,tmp_path):
    binary=_synthetic_header(target)
    digest=sha256(binary).hexdigest()
    evidence=validate_rom(binary,target,expected_sha256=digest)
    assert evidence["sha256"]==digest
    assert evidence["header_magic_verified"]
    assert evidence["correct_machine_region_verified"]
    assert evidence["native_rom_checksum_verified"]
    assert evidence["native_gameplay_executed"] is False
    assert evidence["physical_hardware_verified"] is False
    assert evidence["release_approved"] is False
    assert evidence["distribution_licensed"] is False
    path=tmp_path/("game.sms" if target=="sega_master_system" else "game.gg")
    path.write_bytes(binary)
    assert validate_rom_file(path,target)==validate_rom(binary,target)


def test_wrong_console_code_and_corruption_refused():
    sms=_synthetic_header()
    with pytest.raises(Sega8BitROMError,match="region"):
        validate_rom(sms,"sega_game_gear")
    for damaged in (
        b"MZ"+sms[2:],
        sms[:0x7ff0]+b"DEADROM!"+sms[0x7ff8:],
        sms[:-1]+b"\xFF",
        sms[:11]+b"X"+sms[12:],
        sms[:-1],
        sms+b"\x00",
    ):
        with pytest.raises(Sega8BitROMError):
            validate_rom(damaged,"sega_master_system")


def test_additive_checksum_cannot_substitute_for_content_sha256():
    original=_synthetic_header()
    modified=bytearray(original)
    modified[15]=1
    modified[16]=255  # 1 + 255 == 0 mod 256, not 0 mod 65536
    # Compensate the additive checksum exactly with a same-valued swap.
    modified[15]=ord("E")
    modified[16]=ord("T")
    modified[0],modified[1]=modified[1],modified[0]  # sum preserved
    forged=bytes(modified)
    assert validate_rom(forged,"sega_master_system")["native_rom_checksum_verified"]
    with pytest.raises(Sega8BitROMError,match="digest"):
        validate_rom(forged,"sega_master_system",expected_sha256=sha256(original).hexdigest())


def test_invalid_digest_symlink_and_blank_cartridge_rejected(tmp_path):
    binary=_synthetic_header()
    with pytest.raises(Sega8BitROMError,match="digest"):
        validate_rom(binary,"sega_master_system",expected_sha256="123")
    with pytest.raises(Sega8BitROMError,match="unsupported"):
        validate_rom(binary,"unknown_machine")
    path=tmp_path/"rom.sms"
    path.write_bytes(binary)
    link=tmp_path/"link.sms"
    link.symlink_to(path)
    with pytest.raises(Sega8BitROMError,match="ordinary"):
        validate_rom_file(link,"sega_master_system")
    blank=bytearray(32768)
    blank[0x7ff0:0x7ff8]=b"TMR SEGA"
    blank[0x7fff]=0x4c
    with pytest.raises(Sega8BitROMError,match="no executable payload"):
        validate_rom(bytes(blank),"sega_master_system")
