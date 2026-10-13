"""Original, playable-world-derived hardware cartridge acceptance contracts."""
from __future__ import annotations

from dataclasses import replace
import json
import re

import pytest

from skeleton.ai.game_builder.game_boy_native_export import (
    GameBoySourceError, compile_native_game_boy, export_native_game_boy,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _original_world(*, width: int = 17, height: int = 15, levels: int = 3):
    intent = GameBuildIntent(
        project_id="original-dmg-world", title="Dithered Moon Mazes",
        subtitle="Original portable game", seed=910762, width=width,
        height=height, levels=levels, collectibles_per_level=3,
        hazards_per_level=4, starting_health=4, theme="space",
    )
    return generate_playable_world(intent, authorized=True)


def _owned(world):
    return HomebrewSource(
        project_id=world.intent.project_id,
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",
        evidence_sha256="a" * 64,
        creative_identity=("original tile art", "star maze", "collectible key loop"),
    )


def test_dmg_source_contains_real_8bit_hardware_engine_and_unique_level_maps(tmp_path):
    world = _original_world()
    source = _owned(world)
    result = compile_native_game_boy(world, source, authorized=True)
    assert result == compile_native_game_boy(world, source, authorized=True)
    assert result.artifact_kind == "game_boy_dmg_rgbds_source"
    assert not result.rom_compiled and not result.emulator_verified
    assert "SECTION \"Cartridge Entry\", ROM0[$0100]" in result.asm
    assert "SECTION \"Game State\", WRAM0" in result.asm
    assert "ldh [rLCDC], a" in result.asm
    assert "ld [OAM+1], a" in result.asm
    assert "DEF BG_BYTE_COUNT EQU 576" in result.asm
    assert "DEF LEVEL_COUNT EQU 3" in result.asm
    assert "ld hl, TILEMAP" in result.asm
    assert "call LoadLevel" in result.asm
    assert "GemsRemaining" in result.asm
    assert "Score: ds 1" in result.asm
    assert "GameWon: ds 1" in result.asm
    assert "rgbasm" in result.makefile and "rgblink" in result.makefile
    assert "rgbfix" in result.makefile and "skeleton-original.gb" in result.makefile
    assert not any(key in result.asm for key in ("__WIDTH__", "__MAP_DATA__", "__TILE_BYTES__"))
    assert all(f"LevelMap{i}:" in result.asm for i in range(3))
    assert result.asm.count("    db $") >= 3 * 15
    manifest = json.loads(result.manifest_json)
    assert manifest["levels"] == 3
    assert manifest["width"] == 17 and manifest["height"] == 15
    assert manifest["world_digest"] == world.digest
    assert manifest["source_platform"] == "bandai_wonderswan"
    assert manifest["rom_compiled"] is False
    assert manifest["physical_hardware_verified"] is False
    assert manifest["licensed_distribution"] is False
    assert manifest["safe_reference_moves"] == sum(len(level.safe_solution) for level in world.levels)
    folder = export_native_game_boy(result, tmp_path / "dmg-source", authorized=True)
    assert {p.name for p in folder.iterdir()} == {"main.asm", "Makefile", "manifest.json"}
    assert (folder / "main.asm").read_text(encoding="utf-8") == result.asm
    with pytest.raises(FileExistsError):
        export_native_game_boy(result, folder, authorized=True)


@pytest.mark.parametrize("shape", [(9, 9, 1), (19, 17, 3), (17, 15, 8)])
def test_dmg_source_supported_world_shapes(shape):
    world = _original_world(width=shape[0], height=shape[1], levels=shape[2])
    output = compile_native_game_boy(world, _owned(world), authorized=True)
    assert len(output.asm) > 8000
    assert json.loads(output.manifest_json)["levels"] == shape[2]


def test_game_boy_source_rejects_unsafe_or_incompatible_worlds():
    world = _original_world()
    source = _owned(world)
    with pytest.raises(PermissionError):
        compile_native_game_boy(world, source, authorized=False)
    with pytest.raises(GameBoySourceError, match="mismatch"):
        compile_native_game_boy(world, replace(source, project_id="other-project"), authorized=True)
    with pytest.raises(GameBoySourceError, match="typed original world"):
        compile_native_game_boy("not-a-world", source, authorized=True)
    with pytest.raises(GameBoySourceError, match="DMG"):
        wide = _original_world(width=21)
        compile_native_game_boy(wide, _owned(wide), authorized=True)
    with pytest.raises(PermissionError):
        export_native_game_boy("not-a-project", "unused", authorized=False)


def test_world_affects_dmg_tiles_and_digest():
    one = _original_world()
    two_intent = replace(one.intent, seed=one.intent.seed + 1)
    two = generate_playable_world(two_intent, authorized=True)
    a = compile_native_game_boy(one, _owned(one), authorized=True)
    b = compile_native_game_boy(two, _owned(two), authorized=True)
    assert a.asm != b.asm
    assert a.content_digest != b.content_digest
    assert re.search(r"LevelMap0:\n\s+db \$", a.asm)


def test_dmg_source_never_falsely_certifies_cartridge(tmp_path):
    world = _original_world()
    output = compile_native_game_boy(world, _owned(world), authorized=True)
    assert "release_approved" in output.manifest_json
    assert '"emulator_verified": false' in output.manifest_json
    assert '"rom_compiled": false' in output.manifest_json
    assert not (tmp_path / "not-exported").exists()
    with pytest.raises(PermissionError):
        export_native_game_boy(output, tmp_path / "not-exported", authorized=False)
    assert not (tmp_path / "not-exported").exists()
