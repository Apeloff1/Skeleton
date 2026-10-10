"""Vectrex is Motorola 6809 with a CRT beam, NOT a raster/home computer."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.vectrex_native_export import (
    VectrexNativeError,compile_native_vectrex,export_native_vectrex,
)
from skeleton.ai.game_builder.vectrex_rom import VectrexROMError,verify_vectrex
from skeleton.ai.game_builder.playable_world import GameBuildIntent,generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(seed=198212,width=17,height=15,levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="my-new-vector-dragon",title="Original Vector Stars",
        subtitle="An entirely new 1982 vector fantasy game",seed=seed,
        width=width,height=height,levels=levels,
        collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)


def _rights(w):
    return HomebrewSource(
        project_id=w.intent.project_id,platform_id="vectrex",
        rights_basis="project_owned",evidence_sha256="e"*64,
        creative_identity=("my own star vector world","original dragon silhouette","brand new music patterns"),
    )


def test_original_motorola_6809_real_vector_dragon_source_is_not_html_or_tiles(tmp_path):
    world=_world()
    game=compile_native_vectrex(world,_rights(world),authorized=True)
    assert game==compile_native_vectrex(world,_rights(world),authorized=True)
    assert game.compiled_rom is False and game.vector_display_verified is False
    assert game.artifact_kind=="native_vectrex_mc6809_vector_cartridge_source"
    src=game.asm
    for needle in (
        'FCB     $67,$20','FCC     "GCE 2026"','FDB     SilentMusic',
        'FCC     "ORIGINAL DRAGON STARS"',
        'Wait_Recal      EQU     $F192',
        'Joy_Digital     EQU     $F1F8',
        'Intensity_a     EQU     $F2AB',
        'Moveto_d_7F     EQU     $F2FC',
        'Draw_Line_d     EQU     $F3DF',
        'Reset0Ref       EQU     $F354',
        'DP_to_D0        EQU     $F1AA',
        'Vec_Joy_1_X     EQU     $C81B',
        'Vec_Joy_1_Y     EQU     $C81C',
        'MapRAM          EQU     $C900',
        'Level           EQU     $CB00',
        'HeroX           EQU     $CB01',
        'LDS     #$CBF0',
        'JSR     Wait_Recal',
        'JSR     Joy_Digital',
        'JSR     Draw_Line_d',
        'MUL',
        'LDY     #CELLS',
        'LDU     #MapRAM',
        'DrawHero:',
        'DrawNeighbor:',
        'StageMap0:',
        'StageMap2:',
        'GameSignature:',
    ):
        assert needle in src
    assert "__MAPS__" not in src
    assert "WIDTH           EQU     17" in src
    assert "HEIGHT          EQU     15" in src
    assert "<html" not in src and "javascript" not in src.lower()
    manifest=json.loads(game.manifest_json)
    assert manifest["world_digest"]==world.digest
    assert manifest["target_platform"]=="vectrex"
    assert manifest["physical_shared_ram_kib"]==1
    assert manifest["proprietary_vectrex_bios_included"] is False
    assert manifest["emulator_gameplay_verified"] is False
    assert manifest["commercial_game_license_verified"] is False
    folder=export_native_vectrex(game,tmp_path/"original-vectrex",authorized=True)
    assert {p.name for p in folder.iterdir()}=={"game.asm","Makefile","manifest.json"}
    assert "--format=raw" in (folder/"Makefile").read_text()
    with pytest.raises(FileExistsError):
        export_native_vectrex(game,folder,authorized=True)


@pytest.mark.parametrize("size",((9,9,1),(17,15,3),(17,15,8)))
def test_vectrex_6809_true_RAM_map_and_multi_level_game_source(size):
    width,height,levels=size
    w=_world(width=width,height=height,levels=levels)
    game=compile_native_vectrex(w,_rights(w),authorized=True)
    assert f"WIDTH           EQU     {width}" in game.asm
    assert f"HEIGHT          EQU     {height}" in game.asm
    assert f"LEVELS          EQU     {levels}" in game.asm


def test_vector_console_denies_fake_rights_and_impossible_shared_ram(tmp_path):
    w=_world()
    rights=_rights(w)
    with pytest.raises(PermissionError):
        compile_native_vectrex(w,rights,authorized=False)
    with pytest.raises(VectrexNativeError,match="mismatch"):
        compile_native_vectrex(w,replace(rights,project_id="stolen"),authorized=True)
    wider=_world(width=19)
    with pytest.raises(VectrexNativeError,match="budget"):
        compile_native_vectrex(wider,_rights(wider),authorized=True)
    taller=_world(height=17)
    with pytest.raises(VectrexNativeError,match="budget"):
        compile_native_vectrex(taller,_rights(taller),authorized=True)
    project=compile_native_vectrex(w,rights,authorized=True)
    with pytest.raises(PermissionError):
        export_native_vectrex(project,tmp_path/"not-allowed",authorized=False)
    assert not (tmp_path/"not-allowed").exists()


def _synthetic_6809_structural_fixture():
    # Parser-only fixture: not a fabricated claim of playable guest CPU code.
    from skeleton.ai.game_builder.vectrex_rom import MAGIC,_NATIVE_6809
    blob=bytearray(b"\x20"*1100)
    blob[:len(MAGIC)]=MAGIC
    at=len(MAGIC)
    blob[at:at+6]=b"\x00\xAF\xF8\x50\x30\xB8"
    blob[at+6:at+6+22]=b"ORIGINAL DRAGON STARS\x80\x00"
    blob[100:104]=b"\x10\xCE\xCB\xF0"
    blob[150:153]=b"\x8E\xC9\x00"
    blob[200:202]=b"\x10\x8E"
    at=300
    for op in _NATIVE_6809.values():
        blob[at:at+len(op)]=op
        at+=len(op)+8
    blob[700:711]=b"SKELVEC6809"
    return bytes(blob)


def test_vectrex_real_cartridge_format_bios_instructions_and_tampered_binary():
    program=_synthetic_6809_structural_fixture()
    proof=verify_vectrex(program)
    assert proof["authentic_vectrex_cartridge_header"] is True
    assert proof["motorola_6809_machine_code_verified"] is True
    assert proof["unexpanded_physical_game_ram_bytes"]==1024
    assert proof["independent_vectrex_emulator_playthrough"] is False
    assert proof["third_party_firmware_bundled"] is False
    cases=(
        b"\0\0"+program[2:],
        program[:20]+b"\0"+program[21:],
        program[:100]+b"\0"+program[101:],
        program[:300]+b"\0"+program[301:],
        program[:700]+b"\0"+program[701:],
        program[:-1],
    )
    for case in cases[:-1]:
        with pytest.raises(VectrexROMError):
            verify_vectrex(case)
    with pytest.raises(VectrexROMError):
        verify_vectrex(b"\0"*33000)


def test_original_vectrex_game_seed_changes_machine_6809_source():
    a,b=_world(),_world(seed=198213)
    aa=compile_native_vectrex(a,_rights(a),authorized=True)
    bb=compile_native_vectrex(b,_rights(b),authorized=True)
    assert aa.asm!=bb.asm
    assert aa.content_digest!=bb.content_digest
