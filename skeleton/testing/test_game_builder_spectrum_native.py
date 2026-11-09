"""True ZX Spectrum Z80 hardware-aware original game and cassette admission."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.spectrum_native_export import (
    SpectrumNativeError, compile_native_spectrum, export_native_spectrum,
)
from skeleton.ai.game_builder.spectrum_tap import make_tape, verify_tape, SpectrumTapeError


def _world(seed=198209, width=17, height=15, levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="original-sinclair-maze", title="Stars Beyond Spectrum",
        subtitle="Fully authored 48K original game", seed=seed,
        width=width,height=height,levels=levels,
        collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)


def _rights(world):
    return HomebrewSource(
        project_id=world.intent.project_id,platform_id="sinclair_zx_spectrum",
        rights_basis="project_owned",evidence_sha256="a"*64,
        creative_identity=("my new mazes","my own original puzzles","distinct original star glyphs"),
    )


def test_actual_z80_rom_screen_keyboard_ula_and_original_gameplay(tmp_path):
    world=_world()
    project=compile_native_spectrum(world,_rights(world),authorized=True)
    assert project==compile_native_spectrum(world,_rights(world),authorized=True)
    code=project.asm
    assert "org 32768" in code
    assert "rst 10h" in code
    assert "call 0DAFh" in code
    assert "ld bc, 0FBFEh" in code and "ld bc, 0FDFEh" in code
    assert "in a, (c)" in code and "out (254), a" in code
    assert "halt" in code
    assert "T_WALL: equ 1" in code
    assert "cp T_WALL" in code and "cp T_GEM" in code
    assert "cp T_EXIT" in code and "cp T_HAZARD" in code
    assert "ldir" in code and "MapRAM: ds" in code
    assert "LevelMap0: db" in code and "LevelMap2: db" in code
    assert "LEVELS: equ 3" in code
    assert "__MAP_DATA__" not in code
    assert not project.binary_compiled and not project.emulator_verified
    assert "$(Z80ASM) -o" in project.makefile
    folder=export_native_spectrum(project,tmp_path/"new-zx-source",authorized=True)
    assert {p.name for p in folder.iterdir()}=={
        "game.asm","Makefile","README.txt","manifest.json","make_tap.py",
    }
    with pytest.raises(FileExistsError):
        export_native_spectrum(project,folder,authorized=True)


@pytest.mark.parametrize("shape",((9,9,1),(17,15,3),(29,21,8)))
def test_48k_rom_32_column_original_game_video_envelope(shape):
    w,h,n=shape
    game=_world(width=w,height=h,levels=n)
    z=compile_native_spectrum(game,_rights(game),authorized=True)
    assert f"WIDTH: equ {w}" in z.asm
    assert f"HEIGHT: equ {h}" in z.asm
    assert f"LEVELS: equ {n}" in z.asm


def test_spectrum_refuses_oversize_and_rights_forgery(tmp_path):
    world=_world()
    rights=_rights(world)
    with pytest.raises(PermissionError):
        compile_native_spectrum(world,rights,authorized=False)
    with pytest.raises(SpectrumNativeError,match="mismatch"):
        compile_native_spectrum(world,replace(rights,project_id="other"),authorized=True)
    wide=_world(width=31)
    with pytest.raises(SpectrumNativeError,match="budget"):
        compile_native_spectrum(wide,_rights(wide),authorized=True)
    tall=_world(height=23)
    with pytest.raises(SpectrumNativeError,match="budget"):
        compile_native_spectrum(tall,_rights(tall),authorized=True)
    built=compile_native_spectrum(world,rights,authorized=True)
    with pytest.raises(PermissionError):
        export_native_spectrum(built,tmp_path/"forbidden",authorized=False)
    assert not (tmp_path/"forbidden").exists()


def test_native_zx_spectrum_tape_has_two_real_checksum_protected_code_records():
    program=b"\xFB\xAF\xD3\xFE"+bytes(range(128))
    tape=make_tape(program)
    accepted=verify_tape(tape,program)
    assert accepted["load_address"]==32768
    assert accepted["code_size"]==len(program)
    assert accepted["real_z80_opcode_entry_verified"] is True
    assert accepted["zx_emulator_playthrough_verified"] is False
    assert accepted["rom_firmware_redistributed"] is False
    assert make_tape(program)==tape
    for damaged in (
        tape[:-1],tape+b"\x00",tape[:17]+b"\x03"+tape[18:],
        tape[:30]+bytes((tape[30]^1,))+tape[31:],
        b"MZ"+tape[2:],
    ):
        with pytest.raises(SpectrumTapeError):
            verify_tape(damaged,program)
    with pytest.raises(SpectrumTapeError,match="differs"):
        verify_tape(tape,b"\xFB\xAF\xD3\xFE"+bytes(reversed(range(128))))
    with pytest.raises(SpectrumTapeError):
        make_tape(b"\x00"*132)


def test_original_zx_per_seed_changes_levels_and_machine_executable_source():
    first,other=_world(),_world(seed=198307)
    a=compile_native_spectrum(first,_rights(first),authorized=True)
    b=compile_native_spectrum(other,_rights(other),authorized=True)
    assert a.asm!=b.asm
    assert a.content_digest!=b.content_digest
