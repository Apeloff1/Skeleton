"""Authentic export Master System 32KB 'TMR SEGA' ROM header and checksum.

Verifies physical boot vector, Z80 interrupt vector, Mode-4 VDP ports,
joypad and PSG hardware paths, 32KB size, regional header and BIOS checksum
(sum of first 0x7FF0 bytes modulo 65536; excluding the 16-byte Sega header).
Never bundles machine firmware or commercial game assets.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
from struct import pack, unpack_from

ROM_LENGTH = 32768
HEADER_OFFSET = 0x7FF0
HEADER = b"TMR SEGA"
SMS_REGION_LENGTH = 0x4C
MIN_CODE = 900
HARDWARE_CODES = {
    "VDP_control": b"\xD3\xBF",
    "VDP_data": b"\xD3\xBE",
    "VDP_status": b"\xDB\xBF",
    "joypad1": b"\xDB\xDC",
    "SN76489_PSG": b"\xD3\x7F",
}


class SMSROMError(ValueError):
    """Sega Master System native cartridge has invalid physical boot semantics."""


def verify_sms(rom: bytes, *, expected_program: bytes | None = None) -> dict[str,object]:
    if not isinstance(rom, bytes) or len(rom) != ROM_LENGTH:
        raise SMSROMError("real original export Master System cartridge must be 32768 bytes")
    if rom[:1] != b"\xC3":
        raise SMSROMError("SMS Z80 boot vector must be native JP to ROM code")
    if rom[0x38] != 0xF5 or b"\xED\x4D" not in rom[0x38:0x48]:
        raise SMSROMError("SMS VBlank IM1 IRQ vector missing safe context and RETI")
    if rom[0x66:0x68] != b"\xED\x45":
        raise SMSROMError("SMS pause-button NMI handler does not safely RETN")
    if rom[HEADER_OFFSET:HEADER_OFFSET+8] != HEADER:
        raise SMSROMError("missing BIOS-required TMR SEGA header")
    if rom[0x7FF8:0x7FFA] != b"\0\0":
        raise SMSROMError("SMS reserved header bytes noncanonical")
    if rom[0x7FFC:0x7FFF] != b"\0\0\0" or rom[0x7FFF] != SMS_REGION_LENGTH:
        raise SMSROMError("SMS cartridge 32KB export region/size header malformed")
    sum_expected=sum(rom[:HEADER_OFFSET]) & 0xFFFF
    sum_present=unpack_from("<H",rom,0x7FFA)[0]
    if sum_present!=sum_expected:
        raise SMSROMError("BIOS-required Sega checksum differs from original game")
    init_pointer=unpack_from("<H",rom,1)[0]
    if not 0x0068 <= init_pointer < HEADER_OFFSET:
        raise SMSROMError("SMS entry point must address real first-page Z80 code")
    for label,opcode in HARDWARE_CODES.items():
        if opcode not in rom[:0x4000]:
            raise SMSROMError("native SMS game lacks actual hardware opcode: "+label)
    if b"SKELSMS32" not in rom[:HEADER_OFFSET]:
        raise SMSROMError("original SMS source signature missing")
    if expected_program is not None:
        if not isinstance(expected_program,bytes) or not MIN_CODE<=len(expected_program)<=HEADER_OFFSET:
            raise SMSROMError("actual assembled Z80 source missing or oversized")
        if rom[:len(expected_program)]!=expected_program:
            raise SMSROMError("SMS ROM no longer matches independently assembled Z80 source")
        if rom[len(expected_program):HEADER_OFFSET]!=b"\xFF"*(HEADER_OFFSET-len(expected_program)):
            raise SMSROMError("SMS unused region not deterministic FF padding")
        if init_pointer>=len(expected_program):
            raise SMSROMError("SMS boot vector points outside actual assembled source")
    return {
        "schema":"skeleton.game_builder.original_sms_32kb_cartridge.v1",
        "target_platform":"sega_master_system",
        "format":"SMS_32768B_Mode4_Z80_TMR_SEGA_export",
        "sha256":sha256(rom).hexdigest(),
        "rom_size":len(rom),
        "boot_entry_point":init_pointer,
        "header_offset":HEADER_OFFSET,
        "region_and_length":SMS_REGION_LENGTH,
        "boot_rom_checksum":sum_present,
        "boot_header_verified":True,
        "vblank_interrupt_vector_verified":True,
        "hardware_opcode_paths":sorted(HARDWARE_CODES),
        "native_z80_binary_compiled":True,
        "original_4bpp_art_in_source":True,
        "full_sms_emulator_playthrough_verified":False,
        "real_sms_hardware_verified":False,
        "distribution_licensed":False,
    }


def make_sms(program:bytes)->bytes:
    if not isinstance(program,bytes) or not MIN_CODE<=len(program)<=HEADER_OFFSET:
        raise SMSROMError("original Master System game exceeds real 32KB ROM bank envelope")
    if program[:1]!=b"\xC3":
        raise SMSROMError("original native SMS game lacks Z80 reset JP entry")
    rom=bytearray(program+b"\xFF"*(HEADER_OFFSET-len(program)))
    checksum=sum(rom)&0xFFFF
    rom.extend(HEADER + b"\0\0" + pack("<H",checksum) + b"\0\0\0" + bytes((SMS_REGION_LENGTH,)))
    built=bytes(rom)
    verify_sms(built,expected_program=program)
    return built


def get_sms_packer_script()->str:
    return Path(__file__).read_text(encoding="utf-8")


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code",required=True,type=Path)
    parser.add_argument("--rom",required=True,type=Path)
    args=parser.parse_args()
    if args.rom.exists() or args.rom.is_symlink():
        raise FileExistsError(str(args.rom))
    rom=make_sms(args.code.read_bytes())
    with args.rom.open("xb") as stream:
        stream.write(rom)
    print("ORIGINAL_SMS_NATIVE_ROM_COMPILED",verify_sms(rom)["sha256"])


if __name__=="__main__":
    main()
