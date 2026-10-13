"""Adversarial real MSX1 original Z80 gameplay, BIOS and 16KB ROM contracts."""
from __future__ import annotations

from dataclasses import replace
from struct import pack

import pytest

from skeleton.ai.game_builder.msx1_native_export import (
    MSX1NativeError, compile_native_msx1, export_native_msx1,
)
from skeleton.ai.game_builder.msx1_rom import (
    MSX1ROMError, ROM_LENGTH, BIOS, make_msx1_rom, verify_msx1_rom,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(*, seed=198306, width=17, height=15, levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="new-own-msx1", title="Original MSX Star",
        subtitle="Native MSX Z80 original adventure",
        seed=seed,width=width,height=height,levels=levels,
        collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)


def _rights(world):
    return HomebrewSource(
        project_id=world.intent.project_id,platform_id="msx1",
        rights_basis="project_owned",evidence_sha256="e"*64,
        creative_identity=("own maze puzzles","new crystalline pixel art","original progression and chimes"),
    )


def test_real_40column_msx_bios_vdp_sound_and_joy1_z80_source(tmp_path):
    world=_world()
    project=compile_native_msx1(world,_rights(world),authorized=True)
    assert project==compile_native_msx1(world,_rights(world),authorized=True)
    assert project.artifact_kind=="native_msx1_z80_16kb_bios_rom_source"
    assert project.native_rom_built is False
    assert project.emulator_gameplay_verified is False
    asm=project.asm
    for symbol,address in (
        ("MSX_INITXT","0006Ch"), ("MSX_CHGCLR","00062h"),
        ("MSX_CHPUT","000A2h"), ("MSX_CHSNS","0009Ch"),
        ("MSX_CHGET","0009Fh"), ("MSX_GTSTCK","000D5h"),
        ("MSX_POSIT","000C6h"), ("MSX_BEEP","000C0h"),
    ):
        assert f"{symbol}: equ {address}" in asm
    assert "org 04000h" in asm
    assert 'db "AB"' in asm
    assert "dw GameStart" in asm
    assert "ldir" in asm
    assert "MapRAM: equ 0C100h" in asm
    assert "ReadJoystick:" in asm and "ReadKeyboard:" in asm
    assert "call MSX_INITXT" in asm
    assert "call MSX_CHGCLR" in asm
    assert "call MSX_BEEP" in asm
    assert "call MSX_CHPUT" in asm
    assert "call MSX_GTSTCK" in asm
    assert "halt" in asm
    assert "call MSX_POSIT" in asm
    assert "GameSignature: db" in asm
    assert "StageMap0: db" in asm and "StageMap2: db" in asm
    assert "__LEVEL_MAPS__" not in asm
    assert "WIDTH: equ 17" in asm
    assert "LEVELS: equ 3" in asm
    assert "$(Z80ASM) -o" in project.makefile
    manifest=__import__("json").loads(project.manifest_json)
    assert manifest["world_digest"]==world.digest
    assert manifest["target_platform"]=="msx1"
    assert manifest["native_rom_built"] is False
    assert manifest["emulator_gameplay_verified"] is False
    assert manifest["distribution_licensed"] is False
    root=export_native_msx1(project,tmp_path/"new-original-msx",authorized=True)
    assert {p.name for p in root.iterdir()}=={
        "game.asm","Makefile","README.txt","manifest.json","make_rom.py",
    }
    with pytest.raises(FileExistsError):
        export_native_msx1(project,root,authorized=True)


@pytest.mark.parametrize("dimensions", ((9,9,1),(17,15,3),(37,21,8)))
def test_msx1_respects_16kb_game_and_40x24_bios_screen_envelope(dimensions):
    w,h,n=dimensions
    world=_world(width=w,height=h,levels=n)
    project=compile_native_msx1(world,_rights(world),authorized=True)
    assert f"WIDTH: equ {w}" in project.asm
    assert f"HEIGHT: equ {h}" in project.asm
    assert f"LEVELS: equ {n}" in project.asm


def test_msx1_rejects_rights_forgery_and_hardware_oversize(tmp_path):
    w=_world()
    author=_rights(w)
    with pytest.raises(PermissionError):
        compile_native_msx1(w,author,authorized=False)
    with pytest.raises(MSX1NativeError,match="match"):
        compile_native_msx1(w,replace(author,project_id="other"),authorized=True)
    wide=_world(width=39)
    with pytest.raises(MSX1NativeError,match="budget"):
        compile_native_msx1(wide,_rights(wide),authorized=True)
    tall=_world(height=23)
    with pytest.raises(MSX1NativeError,match="budget"):
        compile_native_msx1(tall,_rights(tall),authorized=True)
    result=compile_native_msx1(w,author,authorized=True)
    with pytest.raises(PermissionError):
        export_native_msx1(result,tmp_path/"denied",authorized=False)
    assert not (tmp_path/"denied").exists()


def _fake_msx_program():
    # Only tests the file parser, never claimed as playable native code.
    blob=bytearray(1024)
    blob[:2]=b"AB"
    blob[2:4]=pack("<H",0x4010)
    blob[0x10:0x15]=b"\xAF\x32\x00\xC0\xC9"
    i=100
    for code in BIOS.values():
        blob[i:i+3]=bytes((0xCD,code & 255,code >> 8))
        i+=3
    blob[300:308]=b"SKELMSX1"
    return bytes(blob)


def test_real_16kb_ab_cartridge_header_bios_opcode_and_originality_parser():
    source=_fake_msx_program()
    rom=make_msx1_rom(source)
    receipt=verify_msx1_rom(rom,expected_program=source)
    assert len(rom)==ROM_LENGTH
    assert rom[:2]==b"AB"
    assert receipt["entry_point"]==0x4010
    assert receipt["native_z80_binary_compiled"] is True
    assert receipt["msx1_emulator_playthrough_verified"] is False
    assert receipt["real_msx1_hardware_verified"] is False
    assert receipt["distribution_licensed"] is False
    assert receipt["native_z80_bios_calls_verified"]==sorted(BIOS)
    damaged_cases=(
        b"MZ"+rom[2:],
        rom[:-1],
        rom[:2]+pack("<H",0x8000)+rom[4:],
        rom[:4]+pack("<H",0x2000)+rom[6:],
        rom[:10]+b"\x01"+rom[11:],
        rom[:16]+b"\x00"+rom[17:],
        rom[:300]+b"BADMSX00"+rom[308:],
        rom[:100]+b"\0\0\0"+rom[103:],
    )
    for payload in damaged_cases:
        with pytest.raises(MSX1ROMError):
            verify_msx1_rom(payload,expected_program=source)
    with pytest.raises(MSX1ROMError,match="differs"):
        verify_msx1_rom(rom,expected_program=source[:-1]+b"\xFF")
    with pytest.raises(MSX1ROMError,match="budget"):
        make_msx1_rom(b"\0"*16385)


def test_original_msx1_game_is_deterministic_and_seed_changes_real_machine_code():
    a,b=_world(),_world(seed=198307)
    aa=compile_native_msx1(a,_rights(a),authorized=True)
    bb=compile_native_msx1(b,_rights(b),authorized=True)
    assert aa.asm!=bb.asm
    assert aa.content_digest!=bb.content_digest
