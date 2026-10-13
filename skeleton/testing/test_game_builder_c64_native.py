"""Game-world-specific Commodore 64 source compilation and hardware fit contracts."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.c64_native_export import (
    NativeC64Error, compile_native_c64, export_native_c64,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(seed=401984, width=17, height=15, levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="owned-c64-game", title="Original Star Trails",
        subtitle="Real Commodore homebrew", seed=seed,
        width=width, height=height, levels=levels,
        collectibles_per_level=3, hazards_per_level=4,
        starting_health=3, theme="space",
    ), authorized=True)


def _rights(world):
    return HomebrewSource(
        project_id=world.intent.project_id, platform_id="bandai_wonderswan",
        rights_basis="project_owned", evidence_sha256="f"*64,
        creative_identity=("original star tiles", "maze navigation", "original hud"),
    )


def test_c64_native_source_is_actual_6510_io_game_not_html(tmp_path):
    world = _world()
    source = _rights(world)
    project = compile_native_c64(world, source, authorized=True)
    assert project == compile_native_c64(world, source, authorized=True)
    assert project.artifact_kind == "native_c64_cc65_prg_source"
    assert not project.binary_built
    code = project.game_c
    assert "#define SCREEN ((volatile u8*)0x0400)" in code
    assert "#define COLOUR ((volatile u8*)0xD800)" in code
    assert "#define JOY2 (*(volatile u8*)0xDC00)" in code
    assert "#define SID_VOL (*(volatile u8*)0xD418)" in code
    assert "#define RASTER (*(volatile u8*)0xD012)" in code
    assert "game_maps[LEVELS][CELLS]" in code
    assert "runtime_map[index] = T_FLOOR" in code
    assert "if (health == 0) lost = 1" in code
    assert "if ((u8)(level + 1) == LEVELS)" in code
    assert "__LEVELS__" not in code  # no unresolved hardware compile placeholders
    assert "#define LEVELS 3" in code
    assert "__WIDTH__" not in code and "__MAPS__" not in code
    assert "<html" not in code
    assert "$(CL65) -t c64" in project.makefile
    meta = json.loads(project.manifest_json)
    assert meta["world_digest"] == world.digest
    assert meta["target_platform_id"] == "commodore_64"
    assert meta["binary_built"] is False and meta["emulator_verified"] is False
    assert meta["number_of_levels"] == 3
    root = export_native_c64(project, tmp_path / "c64-original", authorized=True)
    assert {p.name for p in root.iterdir()} == {"game.c", "Makefile", "manifest.json"}
    with pytest.raises(FileExistsError):
        export_native_c64(project, root, authorized=True)


def test_c64_source_depends_on_seed_and_never_claims_platform_approval():
    a, b = _world(), _world(seed=401985)
    pa = compile_native_c64(a, _rights(a), authorized=True)
    pb = compile_native_c64(b, _rights(b), authorized=True)
    assert pa.game_c != pb.game_c
    assert pa.content_digest != pb.content_digest
    assert json.loads(pa.manifest_json)["distribution_licensed"] is False
    assert not pa.emulator_verified and not pa.physical_hardware_verified


@pytest.mark.parametrize("shape", ((9,9,1), (19, 17, 3), (37,23,8)))
def test_c64_real_text_screen_budget_accepts_all_bounded_origins(shape):
    world = _world(width=shape[0], height=shape[1], levels=shape[2])
    project = compile_native_c64(world, _rights(world), authorized=True)
    assert f"#define W {shape[0]}" in project.game_c
    assert f"#define H {shape[1]}" in project.game_c
    assert f"#define LEVELS {shape[2]}" in project.game_c


def test_c64_denies_overlarge_maps_rights_mismatch_and_missing_authority(tmp_path):
    world = _world()
    rights = _rights(world)
    with pytest.raises(PermissionError):
        compile_native_c64(world, rights, authorized=False)
    with pytest.raises(NativeC64Error, match="identity mismatch"):
        compile_native_c64(world, replace(rights, project_id="wrong-project"), authorized=True)
    too_wide = _world(width=39)
    with pytest.raises(NativeC64Error, match="screen envelope"):
        compile_native_c64(too_wide, _rights(too_wide), authorized=True)
    too_high = _world(height=25)
    with pytest.raises(NativeC64Error, match="screen envelope"):
        compile_native_c64(too_high, _rights(too_high), authorized=True)
    built = compile_native_c64(world, rights, authorized=True)
    with pytest.raises(PermissionError):
        export_native_c64(built, tmp_path / "never-created", authorized=False)
    assert not (tmp_path / "never-created").exists()
