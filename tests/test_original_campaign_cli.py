"""Production-shaped campaign CLI, verified files and safe no-overwrite export."""
import json
import pytest
from pathlib import Path
from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from scripts.build_original_campaign import build_full_original_campaign,main

GDD="c"*64


def test_full_campaign_cli_builds_runnable_authored_artifacts_and_all_receipts(tmp_path):
    report=build_full_original_campaign(
        "original",gdd_digest=GDD,seed=19,islands=5,
        destination=tmp_path/"game",
    )
    assert report["schema"]=="skeleton.game.original_campaign_cli_report.v1"
    assert report["world_assurance_axes"] == 7
    assert len(report["world_assurance_receipt"]) == 64
    assert report["independent_recompile_verified"]
    assert report["original_generated_meshes"]>10
    assert report["original_npc_cast"]==3
    assert len(report["original_skeletal_rig_digest"])==64
    assert len(report["foot_ik_receipt"])==64
    assert len(report["ragdoll_receipt"])==64
    assert len(report["npc_supply_receipt"])==64
    assert len(report["actor_blocking_receipt"])==64
    assert len(report["controller_parity_receipt"])==64
    assert len(report["soak_recovery_receipt"])==64
    assert report["real_controller_devices_qualified"]==0
    assert len(report["elastic_skin_receipt"])==64
    assert len(report["faction_economy_receipt"])==64
    assert len(report["facial_performance_receipt"])==64
    assert len(report["dragon_visual_receipt"])==64
    assert len(report["controller_latency_receipt"])==64
    assert len(report["production_watchdog_receipt"])==64
    assert report["release_planes_source_checked"]==6
    assert report["original_foliage_instances"]>10
    assert report["source_replayed_story_branches"]==2
    assert report["source_replayed_distinct_endings"]==2
    assert report["native_camera_frame_verification_required"]
    assert len(report["generated_adaptive_music_receipt"])==64
    assert not report["dragon_source_note_promotion_automatic"]
    assert report["narrative_and_game_canon_replay_required"]
    assert report["executed_qa_scenarios"]==14
    assert report["dragon_independently_replayed_objective_routes"]==4
    assert report["source_files"]>20
    assert not report["production_release_approved"]
    root=tmp_path/"game"/"game/frontier"
    assert (root/"expedition.gd").is_file()
    assert (root/"canon.json").is_file()
    assert (root/"controller.json").is_file()
    assert (root/"campaign_provenance.json").is_file()
    assert (root/"assets").is_dir()
    assert (tmp_path/"game"/"project.godot").is_file()


def test_full_campaign_does_not_overwrite_existing_game_sources(tmp_path):
    root=tmp_path/"original"
    root.mkdir()
    (root/"existing.gd").write_text("original",encoding="utf-8")
    with pytest.raises(ExpeditionError,match="exists"):
        build_full_original_campaign(
            "original",gdd_digest=GDD,seed=11,islands=5,
            destination=root,
        )
    assert (root/"existing.gd").read_text()=="original"


def test_different_controller_and_high_detail_build_more_original_geometry():
    result=build_full_original_campaign(
        "original",gdd_digest=GDD,seed=11,islands=5,
        controller_id="accessible",detail=.85,
    )
    assert result["controller_profile"]=="accessible"
    assert result["independent_recompile_verified"]


def test_original_campaign_cannot_run_without_a_source_gdd():
    with pytest.raises(ExpeditionError,match="source/GDD"):
        build_full_original_campaign(
            "original",gdd_digest="unsafe",seed=11,islands=5,
        )


def test_cli_writes_canonical_json_receipt_and_new_game(tmp_path,capsys):
    root=tmp_path/"game"
    assert main([
        "--project-id","campaign",
        "--gdd-sha256",GDD,
        "--seed","19","--islands","5",
        "--controller","four_button",
        "--export",str(root),
    ])==0
    report=json.loads(capsys.readouterr().out)
    assert report["project"]=="campaign"
    assert report["controller_profile"]=="four_button"
    assert len(report["game_manifest_receipt"])==64
    assert (root/"game/frontier/expedition.tscn").is_file()


def test_cli_builds_real_verified_zip_candidate_without_approval(tmp_path):
    from skeleton.jeeves.game_frontier_campaign_delivery import (
        verify_campaign_bundle, restore_campaign_bundle,
    )
    archive=tmp_path/"original.zip"
    report=build_full_original_campaign(
        "zip_candidate",gdd_digest=GDD,seed=19,islands=5,
        destination=tmp_path/"authored_project",archive=archive,
    )
    assert archive.is_file()
    assert report["delivery_seven_stage_receipts"]==7
    assert len(report["delivery_archive_sha256"])==64
    assert not report["delivery_release_approved"]
    # The actual generated project is source-of-truth, not an invented receipt.
    files={str(p.relative_to(tmp_path/"authored_project")).replace("\\","/"):
           p.read_text(encoding="utf-8") for p in (tmp_path/"authored_project").rglob("*")
           if p.is_file()}
    from skeleton.jeeves.game_frontier_campaign_delivery import prepare_campaign_bundle
    reconstructed=prepare_campaign_bundle(files,project_id="zip_candidate",
        gdd_digest=GDD,world_digest=report["world_digest"])
    assert reconstructed["archive"]==archive.read_bytes()
    assert verify_campaign_bundle(archive.read_bytes(), reconstructed["report"],
                                  original_files=files)["verified"]
    restored=tmp_path/"restored"
    assert restore_campaign_bundle(archive.read_bytes(),reconstructed["report"],restored)["restored"]
    assert (restored/"project.godot").read_bytes()==(tmp_path/"authored_project"/"project.godot").read_bytes()
