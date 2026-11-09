"""Coleco's eight-stage original campaign is a real source game, not a fake counter."""
from __future__ import annotations

import json

import pytest

from scripts.game_builder.native_coleco_ci import emit
from skeleton.ai.game_builder.coleco_native_export import (
    compile_native_coleco,
    ColecoNativeError,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def test_eight_stage_48_crystal_full_original_coleco_campaign_is_playable_source(tmp_path):
    out=tmp_path/"full-original-colecovision"
    receipt=emit(out,campaign=True)
    assert receipt["original_levels"]==8
    assert receipt["total_original_crystals"]==48
    assert receipt["author_campaign_profile"]=="eight_level_48_crystal"
    metadata=json.loads((out/"manifest.json").read_text(encoding="utf-8"))
    assert metadata["gameplay_levels"]==8
    assert metadata["world_digest"]==receipt["game_world_digest"]
    assert metadata["native_binary_compiled"] is False
    assert metadata["redistribution_licensed"] is False
    route=json.loads((out/"independent-guest-reference.json").read_text(encoding="utf-8"))
    assert route["levels"]==8
    assert route["world_digest"]==receipt["game_world_digest"]
    assert route["initial"]["gems_remaining"]==6
    assert route["steps"][-1]["score"]==48
    assert route["steps"][-1]["won"]==1
    assert route["steps"][-1]["lost"]==0
    assert route["steps"][-1]["level"]==7
    assert sum(x["button"]=="right" for x in route["steps"])>10
    assert len(route["steps"])>400
    asm=(out/"game.asm").read_text(encoding="utf-8")
    assert "LEVELS: equ 8" in asm
    assert "GEMS: equ 6" in asm
    assert "StageMap7: db" in asm
    assert "LevelPointers:" in asm
    assert "MapRAM: equ 07000h" in asm
    assert "Stage: equ 07300h" in asm
    assert "SKELCOL32" in asm


def test_full_original_coleco_campaign_does_not_exceed_one_kib_mutable_ram():
    world=generate_playable_world(GameBuildIntent(
        project_id="coleco-maximum-physical-ram",
        title="My Original Largest Coleco World",
        subtitle="Original full native Coleco campaign",
        seed=198307,width=29,height=21,levels=8,
        collectibles_per_level=6,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)
    owned=HomebrewSource(
        project_id=world.intent.project_id,platform_id="colecovision",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("original large Coleco maze","new crystal collection","new gameplay"),
    )
    native=compile_native_coleco(world,owned,authorized=True)
    assert "WIDTH: equ 29" in native.asm
    assert "HEIGHT: equ 21" in native.asm
    assert "CELLS: equ WIDTH*HEIGHT" in native.asm
    assert "StageMap7: db" in native.asm
    assert native.binary_compiled is False


def test_coleco_campaign_requires_independent_native_rights_and_winning_reference():
    w=generate_playable_world(GameBuildIntent(
        project_id="campaign-authorization-unique",
        title="Distinct Coleco Original",
        subtitle="New homebrew game",
        seed=198306,width=17,height=15,levels=8,
        collectibles_per_level=6,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)
    rights=HomebrewSource(
        project_id=w.intent.project_id,platform_id="colecovision",
        rights_basis="project_owned",evidence_sha256=w.digest,
        creative_identity=("novel levels","author assets","distinct music"),
    )
    with pytest.raises(PermissionError):
        compile_native_coleco(w,rights,authorized=False)
    result=compile_native_coleco(w,rights,authorized=True)
    assert result.cpu_playthrough_verified is False
    assert result.physical_hardware_verified is False
