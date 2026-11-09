"""Original CGB RGB555 register, VRAM banking and real cartridge-authoring contracts."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.game_boy_color_native_export import (
    GameBoyColorSourceError, compile_native_game_boy_color,
    export_native_game_boy_color,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _world(seed=104986, width=17, height=15, levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="fully-original-cgb", title="Star Color",
        subtitle="New RGB555 hardware native homebrew",seed=seed,
        width=width,height=height,levels=levels,
        collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="space",
    ),authorized=True)


def _source(world):
    return HomebrewSource(
        project_id=world.intent.project_id,
        platform_id="nintendo_game_watch",
        rights_basis="project_owned", evidence_sha256="a"*64,
        creative_identity=("original star maze","own colorful sprite tiles","distinctive exit puzzles"),
    )


def test_cgb_real_rgb555_hardware_palette_vram_and_multilevel_attrs(tmp_path):
    game=_world()
    project=compile_native_game_boy_color(game,_source(game),authorized=True)
    assert project==compile_native_game_boy_color(game,_source(game),authorized=True)
    assert project.artifact_kind=="native_cgb_rgbds_rgb555_attribute_rom_source"
    assert project.binary_compiled is False and project.cgb_emulator_verified is False
    code=project.asm
    for real_register in ("$FF4F","$FF68","$FF69","$FF6A","$FF6B"):
        assert real_register in code
    assert "ldh [rVBK], a" in code
    assert "ldh [rBCPD], a" in code
    assert "ldh [rOCPD], a" in code
    assert "call InitCGBPalettes" in code
    assert "call LoadCGBAttributes" in code
    assert "CGBAttributeMap0:" in code and "CGBAttributeMap2:" in code
    assert "CGBAttributePointers:" in code
    assert "CGBBackgroundPalette:" in code and "CGBSpritePalette:" in code
    assert "__ATTR_MAPS__" not in code
    assert "$(RGBFIX) -v -C -p 0 -t SKELCOLOR $@" in project.makefile
    assert "skeleton-original.gbc" in project.makefile
    assert "skeleton-original.gb\n" not in project.makefile
    receipt=json.loads(project.manifest_json)
    assert receipt["platform"]=="nintendo_game_boy_color"
    assert receipt["world_digest"]==game.digest
    assert receipt["background_palettes"]==8
    assert receipt["independent_original_tile_palettes"]==5
    assert receipt["vram_bank1_tile_attributes"] is True
    assert receipt["native_color_rom_compiled"] is False
    assert receipt["cgb_emulator_playthrough_verified"] is False
    assert receipt["licensed_distribution"] is False
    out=export_native_game_boy_color(project,tmp_path/"original-color-cart",authorized=True)
    assert {p.name for p in out.iterdir()}=={"main.asm","Makefile","manifest.json"}
    with pytest.raises(FileExistsError):
        export_native_game_boy_color(project,out,authorized=True)


def test_color_cartridge_source_is_derived_from_each_authored_world():
    a=_world()
    b=_world(seed=104987)
    ga=compile_native_game_boy_color(a,_source(a),authorized=True)
    gb=compile_native_game_boy_color(b,_source(b),authorized=True)
    assert ga.asm!=gb.asm
    assert ga.content_digest!=gb.content_digest
    assert ga.manifest_json!=gb.manifest_json


def test_color_backend_refuses_authority_mismatch_and_too_wide_world(tmp_path):
    game=_world()
    rights=_source(game)
    with pytest.raises(PermissionError):
        compile_native_game_boy_color(game,rights,authorized=False)
    with pytest.raises(GameBoyColorSourceError,match="mismatch"):
        compile_native_game_boy_color(game,replace(rights,project_id="foreign"),authorized=True)
    wide=_world(width=21)
    with pytest.raises(GameBoyColorSourceError,match="budget"):
        compile_native_game_boy_color(wide,_source(wide),authorized=True)
    built=compile_native_game_boy_color(game,rights,authorized=True)
    with pytest.raises(PermissionError):
        export_native_game_boy_color(built,tmp_path/"denied",authorized=False)
    assert not (tmp_path/"denied").exists()
