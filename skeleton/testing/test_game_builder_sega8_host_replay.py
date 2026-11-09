"""Actual emitted Sega game C vs independent multi-stage original replay.

Host-side C execution deliberately does not claim a playable Z80 cartridge.
"""
from __future__ import annotations

from dataclasses import replace
import json
import shutil

import pytest

from scripts.game_builder.native_sega_8bit_ci import emit
from scripts.game_builder.sega8_source_replay import (
    Sega8HostReplayError, export_host_reference, plan_host_reference,
    run_host_replay,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.sega_8bit_native_export import (
    compile_native_sega_8bit, export_native_sega_8bit,
)


@pytest.mark.skipif(not shutil.which("gcc"), reason="real host C compiler required")
@pytest.mark.parametrize("target", ("sega_master_system", "sega_game_gear"))
def test_real_original_native_game_c_matches_every_source_game_action(
    tmp_path, target,
):
    authorship=tmp_path/"original-authorship.txt"
    authorship.write_text(
        "Independently drawn tiles, companion animations and original maze.\n",
        encoding="utf-8",
    )
    project=tmp_path/target
    reference=tmp_path/(target+"-expected-route.json")
    emission=emit(target,project,authorship,reference_out=reference)
    report=run_host_replay(project,reference)
    assert report["target"]==target
    assert report["source_content_digest"]==emission["source_content_digest"]
    assert report["world_digest"]==emission["world_digest"]
    assert report["original_levels_verified"]==3
    assert report["original_controller_actions_verified"]>50
    assert report["native_game_c_compiled_and_executed_on_host"] is True
    assert report["original_score_and_screen_state_verified"] is True
    assert report["original_companion_rank_progression_verified"] is True
    assert report["original_native_solution_attract_mode_host_verified"] is True
    assert report["original_demo_controller_actions_verified"] == report["original_controller_actions_verified"]
    assert len(report["original_demo_screen_trace_sha256"]) == 64
    assert report["full_console_emulator_playthrough_verified"] is False
    assert report["native_z80_rom_executed"] is False
    assert report["physical_hardware_verified"] is False
    assert report["release_approved"] is False


@pytest.mark.skipif(not shutil.which("gcc"), reason="real host C compiler required")
def test_eight_levels_cross_999_score_and_seven_bond_thresholds_on_actual_c(tmp_path):
    world=generate_playable_world(GameBuildIntent(
        project_id="original-bond-progression",
        title="Independently Authored Eight World Trials",
        subtitle="original content and noncommercial proof",
        seed=90210,width=17,height=15,
        levels=8,collectibles_per_level=6,hazards_per_level=4,
        starting_health=4,theme="arcade",
    ),authorized=True)
    rights=HomebrewSource(
        project_id=world.intent.project_id,
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("new original gameplay","unlicensed-free source artwork"),
    )
    project=compile_native_sega_8bit(
        world,rights,"sega_game_gear",
        authorized=True,reduced_motion=True,audio_enabled=False,
    )
    source=tmp_path/"full-game"
    export_native_sega_8bit(project,source,authorized=True)
    route_file=tmp_path/"full-reference.json"
    plan=export_host_reference(world,project.content_digest,route_file)
    assert plan["steps"][-1]["level"]==7
    assert plan["steps"][-1]["score"]==1280
    assert plan["steps"][-1]["bond_rank"]==7
    receipt=run_host_replay(source,route_file)
    assert receipt["original_levels_verified"]==8
    assert receipt["original_companion_rank_progression_verified"] is True
    assert receipt["original_score_and_screen_state_verified"] is True
    assert receipt["original_native_solution_attract_mode_host_verified"] is True
    assert receipt["original_demo_controller_actions_verified"] == len(plan["steps"])


@pytest.mark.skipif(not shutil.which("gcc"), reason="real host C compiler required")
def test_guest_c_replay_rejects_forged_trajectory_and_mutated_original_source(tmp_path):
    auth=tmp_path/"author.txt"
    auth.write_text("all artwork created independently",encoding="utf-8")
    source=tmp_path/"source"
    route=tmp_path/"route.json"
    emit("sega_master_system",source,auth,reference_out=route)
    clean_bytes=route.read_bytes()
    data=json.loads(clean_bytes)
    data["steps"][0]["score"]+=10
    route.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(Sega8HostReplayError,match="modified"):
        run_host_replay(source,route)
    route.write_bytes(clean_bytes)
    src_file=source/"game.c"
    src_file.write_text(src_file.read_text(encoding="utf-8")+"\n",
                        encoding="utf-8")
    with pytest.raises(Sega8HostReplayError,match="diverges"):
        run_host_replay(source,route)


def test_sega_host_source_reference_rejects_invalid_source_id_and_false_acceptance():
    world=generate_playable_world(GameBuildIntent(
        project_id="original-reference-test",title="Authored Reference",
        subtitle="independent work",seed=101,width=9,height=9,
        levels=1,collectibles_per_level=1,hazards_per_level=1,
    ),authorized=True)
    with pytest.raises(Sega8HostReplayError,match="exact source"):
        plan_host_reference(world,"origin-story")
    route=plan_host_reference(world,"a"*64)
    assert route["native_cartridge_compiled"] is False
    assert route["z80_cpu_emulator_executed"] is False
    assert route["release_approved"] is False
    assert route["steps"][-1]["won"]==1
