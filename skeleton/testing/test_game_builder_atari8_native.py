"""Native Atari 400/800 original authoring and real 6502 source integrity."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.atari8_native_export import (
    Atari8BitNativeError, compile_native_atari8, export_native_atari8,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(*, seed=198307, width=19, height=17, levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="original-atari-8bit", title="Star Routes",
        subtitle="A true Atari original", seed=seed, width=width,
        height=height, levels=levels, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="space",
    ), authorized=True)


def _source(world):
    return HomebrewSource(
        project_id=world.intent.project_id, platform_id="atari_400_800",
        rights_basis="project_owned", evidence_sha256="a"*64,
        creative_identity=("distinct star-maze progression", "original symbols", "new POKEY tones"),
    )


def test_atari8_generates_genuine_program_specific_antic_gtia_pokey_joystick_source(tmp_path):
    world = _world()
    result = compile_native_atari8(world, _source(world), authorized=True)
    assert result == compile_native_atari8(world, _source(world), authorized=True)
    code = result.game_c
    assert result.artifact_kind == "native_atari_8bit_6502_antic_gtia_pokey_xex_source"
    assert "#include <conio.h>" in code
    assert "0x0278" in code and "STICK0" in code
    assert "0xD40B" in code and "VCOUNT" in code
    assert "0xD200" in code and "AUDF1" in code
    assert "0xD201" in code and "AUDC1" in code
    assert "gotoxy" in code and "cputc" in code
    assert "original_levels[LEVELS][CELLS]" in code
    assert "runtime_map[index] = T_FLOOR;" in code
    assert "if (!health) lost = 1;" in code
    assert "score = (u16)(score + 100);" in code
    assert "#define LEVELS 3" in code
    assert "__MAPS__" not in code and "__HEALTH__" not in code
    assert "<html" not in code
    assert "$(CL65) -t atari" in result.makefile
    manifest = json.loads(result.manifest_json)
    assert manifest["target_platform"] == "atari_400_800"
    assert manifest["original_world_digest"] == world.digest
    assert manifest["playable_reference_actions"] == sum(len(l.safe_solution) for l in world.levels)
    assert manifest["executable_built"] is False
    assert manifest["emulator_gameplay_verified"] is False
    assert manifest["redistribution_approved"] is False
    root = export_native_atari8(result, tmp_path/"new-atari-program", authorized=True)
    assert {p.name for p in root.iterdir()} == {"game.c","Makefile","manifest.json"}
    with pytest.raises(FileExistsError):
        export_native_atari8(result, root, authorized=True)


@pytest.mark.parametrize("shape", ((9,9,1),(19,17,3),(37,22,8)))
def test_atari8_real_40_column_video_budget_across_original_world_shapes(shape):
    width,height,n=shape
    game=_world(width=width,height=height,levels=n)
    source=compile_native_atari8(game,_source(game),authorized=True)
    assert f"#define WIDTH {width}" in source.game_c
    assert f"#define HEIGHT {height}" in source.game_c
    assert f"#define LEVELS {n}" in source.game_c


def test_atari8_rejects_forbidden_rights_and_oversized_video_or_gameplay(tmp_path):
    game=_world()
    rights=_source(game)
    with pytest.raises(PermissionError):
        compile_native_atari8(game,rights,authorized=False)
    with pytest.raises(Atari8BitNativeError,match="mismatch"):
        compile_native_atari8(game,replace(rights,project_id="different"),authorized=True)
    overwide=_world(width=39)
    with pytest.raises(Atari8BitNativeError,match="budget"):
        compile_native_atari8(overwide,_source(overwide),authorized=True)
    overtall=_world(height=24)
    with pytest.raises(Atari8BitNativeError,match="budget"):
        compile_native_atari8(overtall,_source(overtall),authorized=True)
    source=compile_native_atari8(game,rights,authorized=True)
    with pytest.raises(PermissionError):
        export_native_atari8(source,tmp_path/"denied",authorized=False)
    assert not (tmp_path/"denied").exists()


def test_atari8_original_world_seed_changes_executable_logic_and_source_digest():
    a,b=_world(),_world(seed=198309)
    aa=compile_native_atari8(a,_source(a),authorized=True)
    bb=compile_native_atari8(b,_source(b),authorized=True)
    assert aa.game_c != bb.game_c
    assert aa.content_digest != bb.content_digest
    assert "commercial game" not in aa.game_c.lower()



def test_atari_xex_parser_honors_two_byte_sentinel_and_runad(tmp_path):
    from struct import pack
    from scripts.game_builder.native_atari8_ci import verify_xex
    path = tmp_path / "synthetic-structure-only.xex"
    # Synthetic parser test fixture. Only the real CI cc65 output is an actual game.
    first = pack("<HHH", 0xFFFF, 0x2000, 0x244B) + b"A" * 1100
    second = pack("<HH", 0x02E0, 0x02E1) + pack("<H", 0x2000)
    path.write_bytes(first + second)
    r = verify_xex(path)
    assert r["segment_count"] == 2
    assert r["autostart_runad_present"] is True
    assert r["segments"][0]["load_address"] == 0x2000
    assert r["segments"][0]["length"] == 1100
    assert r["atari_os_emulation_verified"] is False
    for broken in (
        first, first + b"\xff",
        pack("<HHH", 0xFFFF, 0x2000, 0x244C) + b"A" * 1100 + second,
        first + pack("<HH", 0x02E1, 0x02E0),
    ):
        path.write_bytes(broken)
        with pytest.raises(ValueError):
            verify_xex(path)
