"""Complete original campaign project: Godot, controllers, assets, Dragon, canon."""
from copy import deepcopy
import json
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_assets import VisualDesign
from skeleton.jeeves.game_frontier_expedition_campaign import (
    compile_original_campaign,verify_original_campaign,
)

GDD="a"*64


def compile_game(**kwargs):
    return compile_original_campaign(
        "campaign",gdd_digest=GDD,seed=13,islands=5,**kwargs,
    )


def test_one_compiler_delivers_playable_original_game_across_all_subsystems():
    built=compile_game()
    manifest=built["manifest"]
    files=built["files"]
    assert manifest["schema"]=="skeleton.game.full_original_campaign_candidate.v1"
    assert manifest["world_digest"]==built["world"].digest
    assert manifest["story_digest"]==built["story"].digest
    assert manifest["actual_qa_cases"]==14
    assert manifest["dragon_verified_route_checks"]==4
    assert manifest["unique_game_assets"]>=10
    assert len(files)>20
    assert "project.godot" in files
    assert "game/frontier/expedition.gd" in files
    assert "game/frontier/controller.json" in files
    assert "game/frontier/canon.json" in files
    assert "game/frontier/dragon_study.json" in files
    assert "game/frontier/qa_report.json" in files
    assert "game/frontier/campaign_provenance.json" in files
    assert any(path.endswith("_lod0.obj") for path in files)
    assert not manifest["production_release_approved"]
    assert not manifest["native_engine_executed_by_compiler"]
    assert not manifest["external_rights_review_signed"]
    assert built["release_review"]["status"]=="blocked"
    assert not built["release_review"]["production_release_approved"]


def test_full_campaign_compilation_is_replay_stable_across_independent_builds():
    a=compile_game()
    b=compile_game()
    assert a["files"]==b["files"]
    assert a["manifest"]==b["manifest"]
    assert verify_original_campaign(
        a,project_id="campaign",gdd_digest=GDD,seed=13,islands=5
    )["all_source_bytes_verified"]


def test_campaign_review_rejects_laundered_native_script_and_asset_provenance():
    a=compile_game()
    bad=deepcopy(a)
    bad["files"]["game/frontier/expedition.gd"]+="\n# unreviewed code"
    with pytest.raises(ExpeditionError,match="differs"):
        verify_original_campaign(
            bad,project_id="campaign",gdd_digest=GDD,seed=13,islands=5)
    bad=deepcopy(a)
    key=next(k for k in bad["files"] if k.endswith("_lod0.obj"))
    bad["files"][key]+="\nf 1 2 3\n"
    with pytest.raises(ExpeditionError,match="differs"):
        verify_original_campaign(
            bad,project_id="campaign",gdd_digest=GDD,seed=13,islands=5)


def test_authoring_seed_changes_source_game_meshes_stories_and_receipts():
    a=compile_game()
    b=compile_original_campaign("campaign",gdd_digest=GDD,seed=14,islands=5)
    assert a["world"].digest!=b["world"].digest
    assert a["story"].digest!=b["story"].digest
    assert a["manifest"]["receipt_digest"]!=b["manifest"]["receipt_digest"]


def test_gamepad_profile_variation_keeps_world_but_changes_release_candidate():
    a=compile_game()
    b=compile_game(controller_id="accessible")
    assert a["world"].digest==b["world"].digest
    assert a["manifest"]["controller_digest"]!=b["manifest"]["controller_digest"]
    assert a["files"]["game/frontier/controller.json"]!=b["files"]["game/frontier/controller.json"]
    assert a["manifest"]["receipt_digest"]!=b["manifest"]["receipt_digest"]


def test_visual_detail_upscale_changes_assets_not_canon_or_world():
    a=compile_game()
    b=compile_game(visual_design=VisualDesign(detail_scale=.95))
    assert a["world"].digest==b["world"].digest
    assert a["story"].digest==b["story"].digest
    assert a["manifest"]["asset_receipt"]!=b["manifest"]["asset_receipt"]
    assert a["manifest"]["receipt_digest"]!=b["manifest"]["receipt_digest"]


def test_game_package_is_source_bound_without_fabricated_native_approval():
    a=compile_game()
    record=json.loads(a["files"]["game/frontier/campaign_provenance.json"])
    assert record["world_digest"]==a["world"].digest
    assert not record["production_release_approved"]
    assert record["file_hashes"]["project.godot"]
    assert record["file_hashes"]["game/frontier/expedition.gd"]
    assert record["dragon_verified_route_checks"]==4
    assert not a["dragon"]["training_weight_promotion_allowed"]
    assert not a["qa"]["release_approved"]



def test_full_campaign_integrates_actual_quest_cinematics_audio_and_render_lod():
    result=compile_game()
    files=result["files"]
    manifest=result["manifest"]
    assert "game/frontier/quests.json" in files
    assert "game/frontier/storyboard.json" in files
    assert "game/frontier/cinematic.gd" in files
    assert "game/frontier/cinematic.tscn" in files
    assert "game/frontier/audio_pcm.json" in files
    assert "game/frontier/audio_manifest.json" in files
    assert "game/frontier/lod_runtime.json" in files
    assert "game/frontier/render_journal.json" in files
    assert "game/frontier/dragon_adversary.json" in files
    assert "game/frontier/dragon_attacks.json" in files
    assert "game/frontier/crash_test_policy.json" in files
    assert result["questbook"].world_digest==result["world"].digest
    assert result["storyboard"].world_digest==result["world"].digest
    assert result["audio"]["score"].world_digest==result["world"].digest
    assert manifest["storyboard_digest"]==result["storyboard"].digest
    assert manifest["original_audio_receipt"]==result["audio"]["manifest"]["receipt_digest"]
    assert manifest["render_lod_receipt"]==result["render"]["receipt_digest"]
    assert manifest["dragon_adversarial_receipt"]==result["dragon_adversary"]["receipt_digest"]
    assert result["dragon_attacks"]["all_attacks_rejected"]
    assert not manifest["fault_recovery_executed_by_compiler"]
    assert not manifest["native_engine_executed_by_compiler"]


def test_integrated_godot_script_executes_game_audio_narrative_lod_and_cinematic():
    built=compile_game()
    gd=built["files"]["game/frontier/expedition.gd"]
    assert "_install_soundscape()" in gd
    assert "AudioStreamWAV.new()" in gd
    assert "func _advance_quests()" in gd
    assert "func _resolve_ending()" in gd
    assert "func _refresh_lod()" in gd
    assert 'EXPEDITION_QUEST' in gd
    assert 'EXPEDITION_ENDING' in gd
    assert "CINEMATIC_SCENE" in gd
    assert "game/frontier/cinematic.gd" in built["files"]


def test_full_campaign_quest_and_audio_source_tamper_fail_independent_recompile():
    candidate=compile_game()
    for path in ("game/frontier/quests.json","game/frontier/audio_pcm.json",
                 "game/frontier/cinematic.gd","game/frontier/lod_runtime.json",
                 "game/frontier/dragon_adversary.json"):
        changed=deepcopy(candidate)
        changed["files"][path]+="\n# unaudited"
        with pytest.raises(ExpeditionError,match="differs"):
            verify_original_campaign(
                changed,project_id="campaign",gdd_digest=GDD,
                seed=13,islands=5,
            )



def test_every_advanced_original_game_system_is_part_of_the_campaign_and_source_replay():
    candidate=compile_game()
    for path in (
        "game/frontier/actor_rig.gd",
        "game/frontier/actor_rig.json",
        "game/frontier/elasticbodyskin3d.json",
        "game/frontier/society.json",
        "game/frontier/performance.gd",
        "game/frontier/performance.json",
        "game/frontier/visual_comparison.json",
        "game/frontier/controller_latency.json",
        "game/frontier/production_telemetry.json",
        "game/frontier/seven_plane_assurance.json",
    ):
        assert path in candidate["files"]
    manifest=candidate["manifest"]
    assert manifest["seven_plane_source_checks"]==6
    assert len(manifest["npc_society_receipt"])==64
    assert len(manifest["elastic_skin_receipt"])==64
    assert candidate["seven_plane_assurance"]["total"]==7
    assert not candidate["seven_plane_assurance"]["production_release_approved"]
    assert not candidate["controller_qa"]["full_hardware_qualification"]
    assert not candidate["dragon_vision"]["neural_weights_promoted"]
    assert verify_original_campaign(
        candidate,project_id="campaign",gdd_digest=GDD,seed=13,islands=5
    )["all_source_bytes_verified"]


def test_advanced_game_artifacts_cannot_be_replaced_after_source_recompile():
    candidate=compile_game()
    for filename in (
        "game/frontier/actor_rig.json",
        "game/frontier/performance.json",
        "game/frontier/society.json",
        "game/frontier/controller_latency.json",
        "game/frontier/seven_plane_assurance.json",
    ):
        tampered=deepcopy(candidate)
        tampered["files"][filename]+="unauthorized content"
        with pytest.raises(ExpeditionError,match="differs"):
            verify_original_campaign(
                tampered,project_id="campaign",gdd_digest=GDD,
                seed=13,islands=5,
            )



def test_additional_seven_original_systems_compile_with_source_receipts_and_replay():
    original=compile_game()
    manifest=original["manifest"]
    for name in (
        "game/frontier/foot_ik.json",
        "game/frontier/ragdoll.json",
        "game/frontier/supply_chain.json",
        "game/frontier/actor_blocking.json",
        "game/frontier/actor_blocking.gd",
        "game/frontier/viewport_capture.gd",
        "game/frontier/controller_era_parity.json",
        "game/frontier/process_soak.json",
    ):
        assert name in original["files"]
    for field in (
        "foot_ik_receipt","ragdoll_receipt","npc_supply_receipt",
        "cinematic_blocking_receipt","controller_parity_receipt",
        "soak_recovery_receipt",
    ):
        assert len(manifest[field])==64
    assert original["controller_parity"]["profile_count"]==7
    assert not original["soak"]["measured_uptime_qualified"]
    assert manifest["actual_hid_devices_qualified"]==0
    assert manifest["native_rgb_frames_captured_by_compiler"]==0


def test_new_physics_and_cinematic_files_fail_independent_source_recompile_on_tampering():
    original=compile_game()
    for name in ("game/frontier/foot_ik.json",
                 "game/frontier/ragdoll.json",
                 "game/frontier/supply_chain.json",
                 "game/frontier/actor_blocking.gd",
                 "game/frontier/controller_era_parity.json"):
        forged=deepcopy(original)
        forged["files"][name]+=" tampered"
        with pytest.raises(ExpeditionError,match="differs"):
            verify_original_campaign(
                forged,project_id="campaign",gdd_digest=GDD,
                seed=13,islands=5,
            )
