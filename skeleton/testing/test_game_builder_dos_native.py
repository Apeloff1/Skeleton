"""Original game generation contracts for authentic 8086 DOS COM programs."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.dos_native_export import (
    NativeDOSError, compile_native_dos, export_native_dos,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(seed=808610, width=19, height=17, levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="my-new-dos-homebrew", title="Own Star Trails",
        subtitle="Authentic original DOS-era gameplay", seed=seed, width=width,
        height=height, levels=levels, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="arcade",
    ), authorized=True)


def _source(world):
    return HomebrewSource(
        project_id=world.intent.project_id,
        platform_id="dos_ega", rights_basis="project_owned",
        evidence_sha256="b" * 64,
        creative_identity=("my distinct maze", "original ascii motif", "my collectible puzzles"),
    )


def test_real_8086_dos_game_contains_playable_maps_keyboard_and_video_logic(tmp_path):
    world = _world()
    a = compile_native_dos(world, _source(world), authorized=True)
    b = compile_native_dos(world, _source(world), authorized=True)
    assert a == b
    assert a.artifact_kind == "native_ibm_pc_dos_8086_com_source"
    assert a.executable_built is False and a.dos_emulator_verified is False
    code = a.game_asm
    assert "cpu 8086" in code
    assert "org 100h" in code
    assert "mov es, ax" in code
    assert "mov ax, 0B800h" in code
    assert "int 10h" in code and "int 16h" in code and "int 21h" in code
    assert "cmp ah, 48h" in code and "cmp ah, 4Dh" in code
    assert "cmp dl, TILE_GEM" in code
    assert "cmp dl, TILE_WALL" in code
    assert "cmp dl, TILE_GOAL" in code
    assert "cmp byte [gems_left], 0" in code
    assert "add word [score], 100" in code
    assert "level_map_0: db" in code
    assert "level_map_1: db" in code
    assert "level_map_2: db" in code
    assert "original_game_signature: db \"SKELDOS1\"" in code
    assert "__WIDTH__" not in code and "__MAP_DATA__" not in code
    assert "nasm" in a.makefile
    manifest = json.loads(a.manifest_json)
    assert manifest["world_digest"] == world.digest
    assert manifest["target_platform_id"] == "dos_vga"
    assert manifest["levels"] == 3
    assert manifest["reference_safe_actions"] == sum(len(l.safe_solution) for l in world.levels)
    assert manifest["executable_built"] is False
    assert manifest["distribution_licensed"] is False
    folder = export_native_dos(a, tmp_path / "original-dos", authorized=True)
    assert {p.name for p in folder.iterdir()} == {"game.asm", "Makefile", "manifest.json"}
    with pytest.raises(FileExistsError):
        export_native_dos(a, folder, authorized=True)


def test_8086_dos_source_changes_with_original_world_and_never_imports_commercial_game():
    world_a = _world()
    world_b = _world(seed=world_a.intent.seed + 1)
    a = compile_native_dos(world_a, _source(world_a), authorized=True)
    b = compile_native_dos(world_b, _source(world_b), authorized=True)
    assert a.game_asm != b.game_asm
    assert a.content_digest != b.content_digest
    assert "copyright nintendo" not in a.game_asm.lower()


@pytest.mark.parametrize("dimensions", ((9,9,1), (19,17,3), (39,23,8)))
def test_8086_original_game_within_real_bios_text_screen_envelope(dimensions):
    w,h,n = dimensions
    world = _world(width=w,height=h,levels=n)
    project = compile_native_dos(world,_source(world),authorized=True)
    assert f"%define WIDTH {w}" in project.game_asm
    assert f"%define HEIGHT {h}" in project.game_asm
    assert f"%define LEVELS {n}" in project.game_asm


def test_native_dos_export_refuses_wrong_authority_bounds_and_rights(tmp_path):
    world = _world()
    source = _source(world)
    with pytest.raises(PermissionError):
        compile_native_dos(world,source,authorized=False)
    with pytest.raises(NativeDOSError,match="mismatch"):
        compile_native_dos(world,replace(source,project_id="wrong"),authorized=True)
    too_wide = _world(width=41)
    with pytest.raises(NativeDOSError,match="budget"):
        compile_native_dos(too_wide,_source(too_wide),authorized=True)
    too_tall = _world(height=25)
    with pytest.raises(NativeDOSError,match="budget"):
        compile_native_dos(too_tall,_source(too_tall),authorized=True)
    built = compile_native_dos(world,source,authorized=True)
    with pytest.raises(PermissionError):
        export_native_dos(built,tmp_path / "denied",authorized=False)
    assert not (tmp_path / "denied").exists()
