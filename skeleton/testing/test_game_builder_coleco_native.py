"""Real ColecoVision Z80 boot/RST/NMI and one-KiB gameplay source checks."""
from __future__ import annotations

from dataclasses import replace
from struct import pack

import pytest

from skeleton.ai.game_builder.coleco_native_export import (
    ColecoNativeError,compile_native_coleco,export_native_coleco,
)
from skeleton.ai.game_builder.coleco_rom import (
    COL_SIZE,HARDWARE,ColecoROMError,make_col,verify_col,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent,generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(*,seed=198207,width=17,height=15,levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="original-coleco-work",title="My New Coleco Adventure",
        subtitle="A novel 1980s style homebrew game",seed=seed,
        width=width,height=height,levels=levels,
        collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)


def _rights(world):
    return HomebrewSource(
        project_id=world.intent.project_id,platform_id="colecovision",
        rights_basis="project_owned",evidence_sha256="f"*64,
        creative_identity=("new original puzzle rules","new star adventure","author-created glyph art"),
    )


def test_coleco_z80_uses_real_os7_rom_start_input_vdp_psg_and_small_memory(tmp_path):
    world=_world()
    game=compile_native_coleco(world,_rights(world),authorized=True)
    assert game==compile_native_coleco(world,_rights(world),authorized=True)
    assert game.binary_compiled is False
    assert game.cpu_playthrough_verified is False
    asm=game.asm
    for code in (
        "org 08000h","dw 0AA55h","dw GameStart",
        "jp VBlankNMI","retn",
        "CV_MODE1: equ 01F85h","CV_ASCII: equ 01F7Fh",
        "VDP_CTRL: equ 0BFh","VDP_DATA: equ 0BEh",
        "JOY1: equ 0FCh","JOY_SELECT: equ 0C0h","PSG: equ 0FFh",
        "MapRAM: equ 07000h","Stage: equ 07300h",
        "ld sp,073F0h","call CV_MODE1","call CV_ASCII",
        "out (JOY_SELECT),a","in a,(JOY1)",
        "out (PSG),a","out (VDP_DATA),a",
        "ldir","StageMap0: db","StageMap2: db",
        "LevelPointers:","SKELCOL32",
    ):
        assert code in asm
    assert "__MAPS__" not in asm and "__POINTERS__" not in asm
    assert "WIDTH: equ 17" in asm and "HEIGHT: equ 15" in asm
    assert "$(Z80ASM) -o" in game.makefile
    import json
    metadata=json.loads(game.manifest_json)
    assert metadata["world_digest"]==world.digest
    assert metadata["ram_physical_kib"]==1
    assert metadata["native_binary_compiled"] is False
    assert metadata["third_party_firmware_included"] is False
    assert metadata["redistribution_licensed"] is False
    folder=export_native_coleco(game,tmp_path/"coleco-native",authorized=True)
    assert {f.name for f in folder.iterdir()}=={
        "game.asm","Makefile","manifest.json","make_col.py",
    }
    with pytest.raises(FileExistsError):
        export_native_coleco(game,folder,authorized=True)


@pytest.mark.parametrize("sizes",((9,9,1),(17,15,3),(29,21,8)))
def test_original_coleco_world_respects_one_kib_ram_and_32x24_screen(sizes):
    w,h,levels=sizes
    world=_world(width=w,height=h,levels=levels)
    game=compile_native_coleco(world,_rights(world),authorized=True)
    assert f"WIDTH: equ {w}" in game.asm
    assert f"HEIGHT: equ {h}" in game.asm
    assert f"LEVELS: equ {levels}" in game.asm


def test_coleco_strictly_refuses_unauthorized_or_oversize_game(tmp_path):
    world=_world()
    rights=_rights(world)
    with pytest.raises(PermissionError):
        compile_native_coleco(world,rights,authorized=False)
    with pytest.raises(ColecoNativeError,match="mismatch"):
        compile_native_coleco(world,replace(rights,project_id="foreign"),authorized=True)
    wide=_world(width=31)
    with pytest.raises(ColecoNativeError,match="budget"):
        compile_native_coleco(wide,_rights(wide),authorized=True)
    tall=_world(height=23)
    with pytest.raises(ColecoNativeError,match="budget"):
        compile_native_coleco(tall,_rights(tall),authorized=True)
    project=compile_native_coleco(world,rights,authorized=True)
    with pytest.raises(PermissionError):
        export_native_coleco(project,tmp_path/"denied",authorized=False)
    assert not (tmp_path/"denied").exists()


def _structural_fixture():
    # Synthetic parser input only, never a claimed runnable emulator artifact.
    b=bytearray(1400)
    b[:2]=bytes.fromhex("55aa")
    b[8:10]=pack("<H",0x7340)
    b[10:12]=pack("<H",0x8050)
    for n in range(7):
        b[12+3*n:15+3*n]=b"\xC9\0\0"
    b[33:36]=b"\xC3\x60\x80"
    b[0x50:0x54]=b"\xF3\x31\xF0\x73"
    b[200:209]=b"SKELCOL32"
    off=260
    for signature in HARDWARE.values():
        b[off:off+len(signature)]=signature
        off+=8
    return bytes(b)


def test_native_coleco_header_and_hardware_paths_reject_rom_tampering():
    source=_structural_fixture()
    rom=make_col(source)
    proof=verify_col(rom,source=source)
    assert len(rom)==COL_SIZE
    assert rom[:2]==b"\x55\xAA"
    assert proof["boot_address"]==0x8050
    assert proof["nmi_address"]==0x8060
    assert proof["physical_ram_kib"]==1
    assert proof["coleco_soft_vectors_verified"] is True
    assert proof["emulator_full_gameplay_verified"] is False
    assert proof["rights_independently_verified"] is False
    bad=(
        b"AB"+rom[2:],
        rom[:-1],
        rom[:8]+b"\0\0"+rom[10:],
        rom[:10]+pack("<H",0x7000)+rom[12:],
        rom[:12]+b"\0"+rom[13:],
        rom[:33]+b"\0"+rom[34:],
        rom[:0x50]+b"\0"+rom[0x51:],
        rom[:200]+b"BADCART!!"+rom[209:],
        rom[:260]+b"\0"*3+rom[263:],
    )
    for candidate in bad:
        with pytest.raises(ColecoROMError):
            verify_col(candidate,source=source)
    with pytest.raises(ColecoROMError,match="no longer matches"):
        verify_col(rom,source=source[:-1]+b"\xA5")
    with pytest.raises(ColecoROMError):
        make_col(b"\0"*COL_SIZE)


def test_coleco_new_world_seed_changes_real_z80_program():
    a,b=_world(),_world(seed=198208)
    ca=compile_native_coleco(a,_rights(a),authorized=True)
    cb=compile_native_coleco(b,_rights(b),authorized=True)
    assert ca.asm!=cb.asm
    assert ca.content_digest!=cb.content_digest
