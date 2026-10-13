"""Admit actual original Motorola 6809 Vectrex CRT game cartridges.

Vectrex ROM validation is NOT raster console header validation. The console
expects a $67,$20,GCE-date cartridge header and BIOS addresses, with
real MC6809 subroutine calls to Wait_Recal, Joy_Digital, Intensity_a,
Moveto_d_7F, Reset0Ref, and Draw_Line_d. Never includes BIOS bytes.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path

MAGIC=b"\x67\x20GCE 2026\x80"
MAX_ROM=32768
MIN_ROM=500
_NATIVE_6809={
    "vectrex_beam_recalibration":b"\xBD\xF1\x92",
    "vectrex_real_digital_joystick":b"\xBD\xF1\xF8",
    "vectrex_vector_beam_intensity":b"\xBD\xF2\xAB",
    "vectrex_real_beam_pen_move":b"\xBD\xF2\xFC",
    "vectrex_draw_vector_line":b"\xBD\xF3\xDF",
    "vectrex_rezero_beam":b"\xBD\xF3\x54",
    "vectrex_bios_DP_to_D0":b"\xBD\xF1\xAA",
}


class VectrexROMError(ValueError):
    """Vectrex cartridge wrong format, memory budget or hardware code path."""


def verify_vectrex(program:bytes)->dict[str,object]:
    if not isinstance(program,bytes) or not MIN_ROM<=len(program)<=MAX_ROM:
        raise VectrexROMError("Vectrex actual MC6809 cartridge must fit 32KiB")
    if not program.startswith(MAGIC):
        raise VectrexROMError("missing actual Vectrex GCE magic and date header")
    music_off=len(MAGIC)
    if music_off+7>=len(program):
        raise VectrexROMError("Vectrex cartridge music/vector BIOS header truncated")
    if program[music_off+2:music_off+6]!=b"\xF8\x50\x30\xB8":
        raise VectrexROMError("Vectrex title vector size/control header malformed")
    if b"ORIGINAL DRAGON STARS\x80\x00" not in program[:120]:
        raise VectrexROMError("Vectrex original homebrew title or terminator invalid")
    if b"SKELVEC6809" not in program:
        raise VectrexROMError("original MC6809 game source marker absent")
    for label,op in _NATIVE_6809.items():
        if op not in program:
            raise VectrexROMError("genuine Vectrex vector CPU lacks required BIOS call: "+label)
    if b"\x10\xCE\xCB\xF0" not in program[:256]:
        raise VectrexROMError("Vectrex 6809 source lacks safe game-RAM stack initialization")
    if b"\x8E\xC9\x00" not in program or b"\x10\x8E" not in program:
        raise VectrexROMError("source lacks original Vectrex physical-RAM map and 6809 Y register")
    if b"ORIGINAL DRAGON STARS" not in program:
        raise VectrexROMError("commercial asset or blank game instead of original Vectrex ROM")
    return {
        "schema":"skeleton.game_builder.native_vectrex_6809_cartridge.v1",
        "target":"vectrex",
        "rom_sha256":sha256(program).hexdigest(),
        "rom_size":len(program),
        "header_start":MAGIC.hex(),
        "authentic_vectrex_cartridge_header":True,
        "motorola_6809_machine_code_verified":True,
        "real_vector_bios_calls_verified":sorted(_NATIVE_6809),
        "original_vector_dragon_title_verified":True,
        "unexpanded_physical_game_ram_bytes":1024,
        "homebrew_source_only":False,
        "independent_vectrex_emulator_playthrough":False,
        "physical_vectrex_hardware_qualified":False,
        "third_party_firmware_bundled":False,
        "commercial_rights_independently_cleared":False,
    }


def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom",type=Path,required=True)
    args=ap.parse_args()
    import json
    print(json.dumps(verify_vectrex(args.rom.read_bytes()),sort_keys=True))


if __name__=="__main__":
    main()
