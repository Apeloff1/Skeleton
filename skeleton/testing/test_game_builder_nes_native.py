"""Real 6502 NES NROM source encoding and original-game integrity checks."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.nes_native_export import (
    NativeNESError, compile_native_nes, export_native_nes,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(*, seed: int = 73018, width: int = 19, height: int = 17, levels: int = 3):
    return generate_playable_world(GameBuildIntent(
        project_id="authored-nes-world", title="Original Famicom Stars",
        subtitle="Native NROM", seed=seed, width=width, height=height,
        levels=levels, collectibles_per_level=3, hazards_per_level=4, theme="arcade",
        starting_health=4,
    ), authorized=True)


def _source(world):
    return HomebrewSource(
        project_id=world.intent.project_id,
        platform_id="bandai_wonderswan", rights_basis="project_owned",
        evidence_sha256="f" * 64,
        creative_identity=("original maze route", "homebrew tile art", "crystal navigation"),
    )


def test_native_nes_rom_generator_has_real_6502_ppu_memory_map_and_original_levels(tmp_path):
    world = _world()
    original = compile_native_nes(world, _source(world), authorized=True)
    again = compile_native_nes(world, _source(world), authorized=True)
    assert original == again
    assert original.artifact_kind == "nes_nrom256_ca65_original_game_source"
    assert not original.cartridge_built and not original.hardware_verified
    assert '.segment "HEADER"' in original.asm
    assert '.segment "ZEROPAGE"' in original.asm
    assert '.segment "VECTORS"' in original.asm
    assert '.segment "CHARS"' in original.asm
    assert '.byte "NES", $1A, 2, 1, 0, 0' in original.asm
    assert "MAP_RAM = $0300" in original.asm
    assert "sta $2007" in original.asm
    assert "sta $4014" in original.asm
    assert "lda $4016" in original.asm
    assert "jsr EraseGemTile" in original.asm
    assert "GameWon" in original.asm
    assert "LevelMap0:" in original.asm
    assert "LevelMap1:" in original.asm
    assert "LevelMap2:" in original.asm
    assert not any(token in original.asm for token in (
        "__MAPS__", "__TILES__", "__WIDTH__", "__HEALTH__", "__LEVEL_COUNT__",
    ))
    assert "start=$8000" in original.linker_cfg
    assert "size=$2000" in original.linker_cfg
    assert "ca65" in original.makefile and "ld65" in original.makefile
    meta = json.loads(original.manifest_json)
    assert meta["world_digest"] == world.digest
    assert meta["format"] == "ines_nrom256_mapper0"
    assert meta["levels"] == 3
    assert meta["reference_safe_moves"] == sum(len(level.safe_solution) for level in world.levels)
    assert meta["original_first_controller_action"] == world.levels[0].safe_solution[0]
    assert meta["original_first_player_spawn"] == list(world.levels[0].start)
    from skeleton.ai.game_builder.nes_native_export import _TILE_INDEX
    expected_bg=bytearray()
    for line in world.levels[0].rows:
        expected_bg.extend(_TILE_INDEX[tile] for tile in line)
        expected_bg.extend(bytes(32-len(line)))
    expected_bg.extend(bytes(32*(30-len(world.levels[0].rows))))
    from hashlib import sha256
    assert len(expected_bg)==960
    assert meta["original_stage_zero_bg_sha256"]==sha256(expected_bg).hexdigest()
    assert meta["cartridge_built"] is False
    assert meta["hardware_verified"] is False
    out = export_native_nes(original, tmp_path / "nes-source", authorized=True)
    assert {p.name for p in out.iterdir()} == {
        "main.s", "nes.cfg", "Makefile", "manifest.json",
    }
    with pytest.raises(FileExistsError):
        export_native_nes(original, out, authorized=True)


@pytest.mark.parametrize("shape", [(9, 9, 1), (31, 29, 2), (19, 17, 8)])
def test_nes_tilemap_budget_and_bankless_level_generation(shape):
    world = _world(width=shape[0], height=shape[1], levels=shape[2])
    project = compile_native_nes(world, _source(world), authorized=True)
    assert project.asm.count("LevelMap") >= shape[2]
    assert 'MAP_RAM = $0300' in project.asm


def test_nes_source_rejects_invalid_rights_world_size_and_authorization(tmp_path):
    world = _world()
    source = _source(world)
    with pytest.raises(PermissionError):
        compile_native_nes(world, source, authorized=False)
    with pytest.raises(NativeNESError, match="mismatch"):
        compile_native_nes(world, replace(source, project_id="mismatch"), authorized=True)
    width_overflow = _world(width=33)
    with pytest.raises(NativeNESError, match="envelope"):
        compile_native_nes(width_overflow, _source(width_overflow), authorized=True)
    height_overflow = _world(height=31)
    with pytest.raises(NativeNESError, match="envelope"):
        compile_native_nes(height_overflow, _source(height_overflow), authorized=True)
    project = compile_native_nes(world, source, authorized=True)
    with pytest.raises(PermissionError):
        export_native_nes(project, tmp_path / "not-exported", authorized=False)
    assert not (tmp_path / "not-exported").exists()


def test_nes_world_data_changes_with_seed_and_derives_all_generated_level_maps():
    first = _world()
    second = _world(seed=first.intent.seed + 13)
    a = compile_native_nes(first, _source(first), authorized=True)
    b = compile_native_nes(second, _source(second), authorized=True)
    assert a.asm != b.asm
    assert a.content_digest != b.content_digest
    assert a.manifest_json != b.manifest_json
    assert "ThirdParty" not in a.asm
