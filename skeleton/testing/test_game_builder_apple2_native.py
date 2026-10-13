"""Verify authentic original Apple II keyboard/speaker gameplay and AppleSingle evidence."""
from __future__ import annotations

from dataclasses import replace
import json
from struct import pack

import pytest

from skeleton.ai.game_builder.apple2_native_export import (
    Apple2NativeError, compile_native_apple2, export_native_apple2,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from scripts.game_builder.native_apple2_ci import verify


def _world(*, seed=197906, width=17, height=15, levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="apple-own-project", title="Original Star Lights",
        subtitle="Original classic Apple II game", seed=seed,
        width=width,height=height,levels=levels,
        collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ), authorized=True)


def _rights(world):
    return HomebrewSource(
        project_id=world.intent.project_id,platform_id="atari_400_800",
        rights_basis="project_owned",evidence_sha256="d"*64,
        creative_identity=("original Apple game rules","own sprite glyphs","own speaker notes"),
    )


def test_apple2_generates_real_keyboard_6502_text_mode_and_speaker_source(tmp_path):
    world=_world()
    project=compile_native_apple2(world,_rights(world),authorized=True)
    assert project==compile_native_apple2(world,_rights(world),authorized=True)
    assert project.artifact_kind=="native_apple2_cc65_6502_applesingle_source"
    assert project.binary_compiled is False
    assert project.emulator_verified is False
    c=project.game_c
    assert "#include <conio.h>" in c
    assert "0xC030" in c and "SPEAKER" in c
    assert "cgetc()" in c and "gotoxy" in c
    assert "case 'I':" in c and "case 'K':" in c
    assert "case 'J':" in c and "case 'L':" in c
    assert "writable_map[pos] = T_FLOOR" in c
    assert "health == 0" in c
    assert "score + 100" in c
    assert "authored_maps[LEVELS][CELLS]" in c
    assert "#define LEVELS 3" in c
    assert "__MAPS__" not in c
    assert "<html" not in c
    assert "$(CL65) -t apple2 -O" in project.makefile
    manifest=json.loads(project.manifest_json)
    assert manifest["world_digest"]==world.digest
    assert manifest["runtime_assumption"]=="Apple_II_plus_or_IIe_with_language_card"
    assert manifest["binary_compiled"] is False
    assert manifest["redistribution_licensed"] is False
    root=export_native_apple2(project,tmp_path/"apple-source",authorized=True)
    assert {p.name for p in root.iterdir()}=={"game.c","Makefile","manifest.json"}
    with pytest.raises(FileExistsError):
        export_native_apple2(project,root,authorized=True)


@pytest.mark.parametrize("shape",((9,9,1),(17,15,3),(37,21,8)))
def test_apple_ii_video_bounds_preserve_original_game_content(shape):
    w,h,n=shape
    g=_world(width=w,height=h,levels=n)
    project=compile_native_apple2(g,_rights(g),authorized=True)
    assert f"#define WIDTH {w}" in project.game_c
    assert f"#define HEIGHT {h}" in project.game_c
    assert f"#define LEVELS {n}" in project.game_c


def test_apple_source_denies_rights_forgery_or_unrenderable_world(tmp_path):
    g=_world()
    rights=_rights(g)
    with pytest.raises(PermissionError):
        compile_native_apple2(g,rights,authorized=False)
    with pytest.raises(Apple2NativeError,match="mismatch"):
        compile_native_apple2(g,replace(rights,project_id="fake"),authorized=True)
    overwidth=_world(width=39)
    with pytest.raises(Apple2NativeError,match="budget"):
        compile_native_apple2(overwidth,_rights(overwidth),authorized=True)
    overheight=_world(height=23)
    with pytest.raises(Apple2NativeError,match="budget"):
        compile_native_apple2(overheight,_rights(overheight),authorized=True)
    a=compile_native_apple2(g,rights,authorized=True)
    with pytest.raises(PermissionError):
        export_native_apple2(a,tmp_path/"should-not-exist",authorized=False)
    assert not (tmp_path/"should-not-exist").exists()


def test_apple_single_parser_rejects_nonapple_files_duplicate_forks_and_truncation(tmp_path):
    path=tmp_path/"synthetic.applesingle"
    # Synthetic structural fixture only, NOT native binary gameplay certification.
    header=bytes.fromhex("00051600 00020000")+b"\x00"*16+pack(">H",1)
    table=pack(">III",1,38,1000)
    path.write_bytes(header+table+b"\xAA"*1000)
    proof=verify(path)
    assert proof["applesingle_header_verified"] is True
    assert proof["file_entry_count"]==1
    assert proof["apple_ii_emulator_playthrough_verified"] is False
    for payload in (
        b"MZ"+b"\0"*300,
        header+pack(">III",1,38,1001)+b"\xAA"*1000,
        header+pack(">III",2,38,1000)+b"\xAA"*1000,
        header+pack(">III",1,9999,1000)+b"\xAA"*1000,
    ):
        path.write_bytes(payload)
        with pytest.raises(ValueError):
            verify(path)
