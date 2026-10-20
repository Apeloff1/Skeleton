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
