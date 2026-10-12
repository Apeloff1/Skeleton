"""Validate real OS7 ColecoVision 32KB Z80 cartridge header and native code.

ColecoVision firmware expects either 55AA (direct) or AA55 (title) at
the $8000 entry, a 16-bit game-start pointer at $800A, seven soft RST
dispatch slots and a jump at $8021 for the VBlank NMI vector. Unlike
Sega's TMR SEGA header or the MSX AB header, no checksum is mandated.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
from struct import unpack_from

COL_SIZE=32768
COL_BASE=0x8000
MIN_SOURCE=400
MAGIC=b"\x55\xAA"
HARDWARE={
    "VDP_TMS9918_data":b"\xD3\xBE",
    "VDP_TMS9918_control":b"\xD3\xBF",
    "joystick_1":b"\xDB\xFC",
    "joystick_mode":b"\xD3\xC0",
    "SN76489_PSG":b"\xD3\xFF",
    "Coleco_OS7_MODE1":b"\xCD\x85\x1F",
    "Coleco_OS7_ASCII":b"\xCD\x7F\x1F",
}


class ColecoROMError(ValueError):
    """Non-Coleco, tampered, oversized or nonnative source cartridge."""


def verify_col(rom:bytes,*,source:bytes|None=None)->dict[str,object]:
    if not isinstance(rom,bytes) or len(rom)!=COL_SIZE:
        raise ColecoROMError("ColecoVision unbanked ROM image must be 32KB")
    if rom[:2]!=MAGIC:
        raise ColecoROMError("ColecoVision native direct-boot magic 55AA required")
    if rom[2:8]!=b"\0"*6:
        raise ColecoROMError("ColecoVision BIOS sprite/work header pointers must be unused")
    if unpack_from("<H",rom,8)[0]!=0x7340:
        raise ColecoROMError("ColecoVision player input scratch address wrong")
    boot=unpack_from("<H",rom,10)[0]
    if not 0x8024<=boot<=0xFFFF:
        raise ColecoROMError("ColecoVision BIOS boot pointer outside actual cartridge")
    for n in range(7):
        if rom[0x0C+n*3:0x0C+(n+1)*3]!=b"\xC9\0\0":
            raise ColecoROMError("Coleco OS7 RST soft vector missing safe return stub")
    if rom[0x21]!=0xC3:
        raise ColecoROMError("ColecoVision mandatory OS7 VBlank NMI jump absent")
    nmi=unpack_from("<H",rom,0x22)[0]
    if not 0x8024<=nmi<=0xFFFF:
        raise ColecoROMError("Coleco VBlank handler jumps outside real cartridge")
    if rom[boot-COL_BASE:boot-COL_BASE+4]!=b"\xF3\x31\xF0\x73":
        raise ColecoROMError("Coleco Z80 bootstrap has no physical stack init")
    if b"SKELCOL32" not in rom[:0x6000]:
        raise ColecoROMError("original Coleco machine-source signature missing")
    for name,signature in HARDWARE.items():
        if signature not in rom[:0x6000]:
            raise ColecoROMError("actual Coleco BIOS/hardware machine-code path missing: "+name)
    if source is not None:
        if not isinstance(source,bytes) or not MIN_SOURCE<=len(source)<=COL_SIZE:
            raise ColecoROMError("assembled Coleco game source exceeds 32KB address budget")
        if rom[:len(source)]!=source:
            raise ColecoROMError("Coleco output no longer matches independently assembled Z80")
        if rom[len(source):]!=b"\xFF"*(COL_SIZE-len(source)):
            raise ColecoROMError("Coleco cartridge unused banks are not deterministic FF")
        if boot>=COL_BASE+len(source) or nmi>=COL_BASE+len(source):
            raise ColecoROMError("Coleco VBlank/boot vector points outside native authored code")
    return {
        "schema":"skeleton.game_builder.colecovision_native_cartridge.v1",
        "format":"ColecoVision_32K_Z80_OS7_TMS9918A",
        "native_cartridge_sha256":sha256(rom).hexdigest(),
        "bytes":len(rom),
        "header_magic":MAGIC.hex(),
        "cartridge_base_address":COL_BASE,
        "boot_address":boot,
        "nmi_address":nmi,
        "physical_ram_kib":1,
        "coleco_soft_vectors_verified":True,
        "native_z80_hardware_paths_verified":sorted(HARDWARE),
        "binary_assembled":True,
        "emulator_full_gameplay_verified":False,
        "physical_coleco_hardware_verified":False,
        "rights_independently_verified":False,
        "commercial_game_assets_included":False,
    }


def make_col(source:bytes)->bytes:
    if not isinstance(source,bytes) or not MIN_SOURCE<=len(source)<=COL_SIZE:
        raise ColecoROMError("original Coleco Z80 binary exceeds 32KB ROM limit")
    rom=source+b"\xFF"*(COL_SIZE-len(source))
    verify_col(rom,source=source)
    return rom


def get_col_packer_script()->str:
    return Path(__file__).read_text(encoding="utf-8")


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code",type=Path,required=True)
    parser.add_argument("--rom",type=Path,required=True)
    args=parser.parse_args()
    if args.rom.exists() or args.rom.is_symlink():
        raise FileExistsError(str(args.rom))
    built=make_col(args.code.read_bytes())
    with args.rom.open("xb") as handle:
        handle.write(built)
    print("ORIGINAL_COLECO_Z80_ROM_BUILT",verify_col(built)["native_cartridge_sha256"])

if __name__=="__main__":
    main()
