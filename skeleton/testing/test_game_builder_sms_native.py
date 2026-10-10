"""Real SMS Z80 Mode-4 console art, PSG, joypad and 32KB BIOS ROM checks."""
from __future__ import annotations

from dataclasses import replace
from struct import pack

import pytest

from skeleton.ai.game_builder.sms_native_export import (
    SMSNativeError,_TILES,_CRAM,_tile_bytes,compile_native_sms,export_native_sms,
)
from skeleton.ai.game_builder.sms_rom import (
    SMSROMError,HARDWARE_CODES,ROM_LENGTH,HEADER_OFFSET,make_sms,verify_sms,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent,generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(*,seed=198605,width=17,height=15,levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="new-sms-original",title="Original SMS Maze",
        subtitle="New Mode4 console art",seed=seed,width=width,height=height,
        levels=levels,collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)


def _rights(w):
    return HomebrewSource(
        project_id=w.intent.project_id,platform_id="sega_master_system",
        rights_basis="project_owned",evidence_sha256="a"*64,
        creative_identity=("new authored 4bpp art","new star puzzles","distinct original sound themes"),
    )


def test_sms_real_8x8_4bpp_planar_tile_bytes_and_original_rgb222_cram():
    assert len(_TILES)==20
    assert all(len(pixels)==32 for pixels in _TILES)
    assert any(byte for tile in _TILES for byte in tile)
    assert len(set(_TILES))==len(_TILES)
    assert len(_CRAM)==32
    assert all(0<=c<=0x3F for c in _CRAM)
    assert _tile_bytes(("........",)*8)==tuple([0]*32)
    # Four-plane rows: 0x80 bit represents pixel 0, never an 8bpp bitmap.
    assert _tile_bytes(("w.......",)*8) == tuple([0x80,0,0,0]*8)
    with pytest.raises(ValueError):
        _tile_bytes(("bad",)*8)
    with pytest.raises(ValueError):
        _tile_bytes(("wwwwwwww",)*7)


def test_sms_native_mode4_console_cartridge_is_genuine_and_gameplay_world_derived(tmp_path):
    world=_world()
    a=compile_native_sms(world,_rights(world),authorized=True)
    assert a==compile_native_sms(world,_rights(world),authorized=True)
    assert a.artifact_kind=="native_sms_z80_mode4_32kb_cartridge_source"
    assert a.native_cartridge_compiled is False and a.sms_emulator_playthrough_verified is False
    asm=a.asm
    assert "org 00000h" in asm
    assert "    jp GameStart" in asm
    assert "IRQ:" in asm and "reti" in asm
    assert "NMI:" in asm and "retn" in asm
    assert "VP" not in asm.split("VDP_CTRL:")[0] or "in a, (0BFh)" in asm
    for device in ("VDP_CTRL: equ 0BFh","VDP_DATA: equ 0BEh",
                   "PSG_PORT: equ 07Fh","JOY1_PORT: equ 0DCh"):
        assert device in asm
    assert "out (VDP_DATA), a" in asm
    assert "in a, (JOY1_PORT)" in asm
    assert "out (PSG_PORT), a" in asm
    assert "ld sp, 0DFF0h" in asm
    assert "VRAM_NAME: equ 03800h" in asm
    assert "ld bc, 1536" in asm
    assert "MapRAM: equ 0C100h" in asm
    assert "OriginalCRAM:" in asm and "OriginalTilePixels:" in asm
    assert "TilePixelsEnd:" in asm
    assert "StageMap0: db" in asm and "StageMap2: db" in asm
    assert "LEVELS: equ 3" in asm
    assert "__ART__" not in asm and "__CRAM__" not in asm
    assert "$(Z80ASM) -o" in a.makefile
    receipt=__import__("json").loads(a.manifest_json)
    assert receipt["world_digest"]==world.digest
    assert receipt["target_platform"]=="sega_master_system"
    assert receipt["original_tile_count"]==20
    assert receipt["native_cartridge_compiled"] is False
    assert receipt["sms_emulator_playthrough_verified"] is False
    assert receipt["distribution_licensed"] is False
    root=export_native_sms(a,tmp_path/"original-sms",authorized=True)
    assert {p.name for p in root.iterdir()}=={
        "game.asm","Makefile","README.txt","manifest.json","make_sms.py",
    }
    with pytest.raises(FileExistsError):
        export_native_sms(a,root,authorized=True)


@pytest.mark.parametrize("dimensions",((9,9,1),(17,15,3),(31,21,8)))
def test_sms_original_mode4_video_bounds_across_game_sizes(dimensions):
    w,h,n=dimensions
    game=_world(width=w,height=h,levels=n)
    a=compile_native_sms(game,_rights(game),authorized=True)
    assert f"WIDTH: equ {w}" in a.asm
    assert f"HEIGHT: equ {h}" in a.asm
    assert f"LEVELS: equ {n}" in a.asm


def test_sms_source_rejects_external_project_copy_or_unsafe_too_large_world(tmp_path):
    game=_world()
    rights=_rights(game)
    with pytest.raises(PermissionError):
        compile_native_sms(game,rights,authorized=False)
    with pytest.raises(SMSNativeError,match="mismatch"):
        compile_native_sms(game,replace(rights,project_id="copied"),authorized=True)
    wide=_world(width=33)
    with pytest.raises(SMSNativeError,match="budget"):
        compile_native_sms(wide,_rights(wide),authorized=True)
    tall=_world(height=23)
    with pytest.raises(SMSNativeError,match="budget"):
        compile_native_sms(tall,_rights(tall),authorized=True)
    a=compile_native_sms(game,rights,authorized=True)
    with pytest.raises(PermissionError):
        export_native_sms(a,tmp_path/"denied",authorized=False)
    assert not (tmp_path/"denied").exists()


def _fake_sms_binary():
    # Structural admission fixture only, NOT a commercial or real playable ROM.
    b=bytearray(1400)
    b[:3]=b"\xC3\x70\x00"
    b[0x38:0x40]=b"\xF5\xDB\xBF\xF1\xFB\xED\x4D\x00"
    b[0x66:0x68]=b"\xED\x45"
    at=200
    for opcode in HARDWARE_CODES.values():
        b[at:at+len(opcode)]=opcode
        at+=len(opcode)+1
    b[400:409]=b"SKELSMS32"
    return bytes(b)


def test_export_master_system_native_header_checksum_and_hardware_vectors_fail_closed():
    program=_fake_sms_binary()
    rom=make_sms(program)
    receipt=verify_sms(rom,expected_program=program)
    assert len(rom)==ROM_LENGTH
    assert rom[HEADER_OFFSET:HEADER_OFFSET+8]==b"TMR SEGA"
    assert rom[0x7FFF]==0x4C
    assert receipt["boot_entry_point"]==0x70
    assert receipt["boot_header_verified"] is True
    assert receipt["native_z80_binary_compiled"] is True
    assert receipt["full_sms_emulator_playthrough_verified"] is False
    assert receipt["real_sms_hardware_verified"] is False
    for damage in (
        b"MZ"+rom[2:],
        rom[:-1],
        rom[:0x38]+b"\0"+rom[0x39:],
        rom[:0x66]+b"\0"+rom[0x67:],
        rom[:HEADER_OFFSET]+b"BAD SEGA"+rom[HEADER_OFFSET+8:],
        rom[:0x7FFF]+b"\x4B",
        rom[:0x7FFA]+b"\xFF\xFF"+rom[0x7FFC:],
        rom[:200]+b"\0\0"+rom[202:],
    ):
        with pytest.raises(SMSROMError):
            verify_sms(damage,expected_program=program)
    with pytest.raises(SMSROMError,match="differs"):
        verify_sms(rom,expected_program=program[:-1]+b"\xFE")
    with pytest.raises(SMSROMError):
        make_sms(b"\0"*32768)


def test_new_sms_world_changes_actual_z80_game_map_without_commercial_assets():
    a,b=_world(),_world(seed=198606)
    ga=compile_native_sms(a,_rights(a),authorized=True)
    gb=compile_native_sms(b,_rights(b),authorized=True)
    assert ga.asm!=gb.asm
    assert ga.content_digest!=gb.content_digest
