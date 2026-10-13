"""Authentic MSX1 unbanked page-1 16KB Z80 cartridge image packer.

Only accepts a fully assembled MSX page-1 Z80 program with an AB cartridge
header, a valid INIT pointer, blank hook addresses, actual BIOS calls for
hardware graphics/input and independently bounded ROM space. No overlays,
copied machine ROM/BIOS or proprietary system firmware are included.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
from struct import unpack_from

ROM_BASE = 0x4000
ROM_LENGTH = 16 * 1024
HEADER_SIZE = 16
MIN_CODE = 512
INIT_OFFSET = 2
BIOS = {
    "screen0_init": 0x006C,
    "text_character": 0x00A2,
    "key_scan": 0x009C,
    "key_read": 0x009F,
    "joystick_1": 0x00D5,
    "screen_position": 0x00C6,
    "bios_sound": 0x00C0,
}


class MSX1ROMError(ValueError):
    """MSX1 original cartridge header, load envelope or hardware evidence invalid."""


def verify_msx1_rom(rom: bytes, *, expected_program: bytes | None = None) -> dict[str, object]:
    if not isinstance(rom, bytes) or len(rom) != ROM_LENGTH:
        raise MSX1ROMError("authentic native MSX1 page-1 cartridge must be 16KB")
    if rom[:2] != b"AB":
        raise MSX1ROMError("missing actual MSX AB cartridge entry header")
    init, statement, device, basic = (
        unpack_from("<H", rom, n) [0] for n in (2, 4, 6, 8)
    )
    if not 0x4010 <= init < 0x8000:
        raise MSX1ROMError("MSX1 cartridge INIT pointer outside 16KB ROM page")
    if (statement, device, basic) != (0, 0, 0) or rom[10:16] != b"\0" * 6:
        raise MSX1ROMError("MSX1 ROM has unsafe nonempty cartridge hooks or reserved header")
    if expected_program is not None:
        if (not isinstance(expected_program, bytes)
                or len(expected_program) < MIN_CODE or len(expected_program) > ROM_LENGTH):
            raise MSX1ROMError("expected original Z80 program length invalid")
        if rom[:len(expected_program)] != expected_program:
            raise MSX1ROMError("MSX cartridge source differs from assembled authentic Z80 code")
        if rom[len(expected_program):] != b"\xFF" * (ROM_LENGTH-len(expected_program)):
            raise MSX1ROMError("MSX unused ROM region is not deterministic FF padding")
        if init >= ROM_BASE + len(expected_program):
            raise MSX1ROMError("cartridge INIT jumps outside assembled original program")
    if rom[init-ROM_BASE:init-ROM_BASE+2] != b"\xAF\x32":
        raise MSX1ROMError("native MSX init does not begin with expected Z80 XOR/register state")
    for label, target in BIOS.items():
        signature = bytes((0xCD, target & 0xFF, target >> 8))
        if signature not in rom[:8192]:
            raise MSX1ROMError("native MSX game missing real BIOS hardware call: " + label)
    if b"SKELMSX1" not in rom[:8192]:
        raise MSX1ROMError("original Z80 ROM provenance signature absent")
    return {
        "schema": "skeleton.game_builder.msx1_native_rom_build.v1",
        "target_platform": "msx1",
        "format": "native_msx1_16kb_0x4000_ab_z80_rom",
        "bytes": len(rom),
        "sha256": sha256(rom).hexdigest(),
        "load_address": ROM_BASE,
        "entry_point": init,
        "blank_unused_hooks_verified": True,
        "native_z80_bios_calls_verified": sorted(BIOS),
        "rom_header_integrity_verified": True,
        "rom_originality_signature_verified": True,
        "native_z80_binary_compiled": True,
        "msx1_emulator_playthrough_verified": False,
        "real_msx1_hardware_verified": False,
        "distribution_licensed": False,
    }


def make_msx1_rom(program: bytes) -> bytes:
    if not isinstance(program, bytes) or not MIN_CODE <= len(program) <= ROM_LENGTH:
        raise MSX1ROMError("original MSX1 program exceeds actual 16KB cartridge budget")
    if program[:2] != b"AB":
        raise MSX1ROMError("MSX1 program is not a native cartridge")
    rom = program + b"\xFF" * (ROM_LENGTH-len(program))
    verify_msx1_rom(rom, expected_program=program)
    return rom


def get_rom_packer_script() -> str:
    return Path(__file__).read_text(encoding="utf-8")


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code",required=True,type=Path)
    parser.add_argument("--rom",required=True,type=Path)
    args=parser.parse_args()
    if args.rom.exists() or args.rom.is_symlink():
        raise FileExistsError(str(args.rom))
    rom = make_msx1_rom(args.code.read_bytes())
    with args.rom.open("xb") as stream:
        stream.write(rom)
    print("ORIGINAL_MSX1_CARTRIDGE_WRITTEN", verify_msx1_rom(rom)["sha256"])


if __name__ == "__main__":
    main()
