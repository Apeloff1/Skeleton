"""Actual world geometry LOD selection, view budgets and chained frame notes."""
from copy import deepcopy
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_assets import (
    VisualDesign,forge_expedition_assets,
)
from skeleton.jeeves.game_frontier_expedition_render import (
    LODPolicy,View,plan_game_lod,render_lod_timeline,
)
from tests.test_game_frontier_expedition_godot import world


def sources():
    w=world()
    return w,forge_expedition_assets(w,VisualDesign())["manifest"]


def test_visible_mesh_selection_obeys_real_camera_distance():
    w,assets=sources()
    near=View(1,0,0,0,visibility_m=500)
    far=View(2,900,900,900,visibility_m=4000)
    a=plan_game_lod(w,near,assets)
    b=plan_game_lod(w,far,assets)
    assert a["world_digest"]==w.digest
    assert a["budgeted_visible"]>0
    assert b["budgeted_visible"]>0
    assert a["triangle_count"]<=25000
    assert any(item["lod"]==0 for item in a["meshes"])
    assert all(item["lod"]==2 for item in b["meshes"])
    assert not a["native_render_executed"]
    assert a["measured_native_fps"] is None


def test_low_draw_budget_never_exceeds_real_triangle_count():
    w,assets=sources()
    plan=plan_game_lod(w,View(1,0,0,0),assets,
        policy=LODPolicy(triangle_budget=150,max_visible=2))
    assert plan["triangle_count"]<=150
    assert plan["budgeted_visible"]<=2
    assert len(plan["meshes"])<=2


def test_camera_motion_generates_ordered_hash_linked_source_frames():
    w,assets=sources()
    frames=[
        View(1,0,0,0),View(2,25,0,5),
        View(3,60,0,5),View(4,100,0,15),
    ]
    report=render_lod_timeline(w,assets,frames)
    assert report["frames"]==4
    assert len(report["records"])==4
    assert report["records"][1]["prior_receipt"]==report["records"][0]["receipt"]
    assert report["receipt_head"]==report["records"][-1]["receipt"]
    assert not report["native_performance_qualified"]
    assert report==render_lod_timeline(w,assets,frames)


def test_lod_hysteresis_prevents_flapping_near_transition():
    w,assets=sources()
    node=w.by_id[w.arrival]
    camera=View(1,node.x_m+82,node.y_m,node.altitude_m)
    original=plan_game_lod(w,camera,assets)
    no_old=next(item["lod"] for item in original["meshes"] if item["waypoint"]==w.arrival)
    kept=plan_game_lod(w,camera,assets,prior={w.arrival:0})
    with_old=next(item["lod"] for item in kept["meshes"] if item["waypoint"]==w.arrival)
    assert no_old==1
    assert with_old==0


def test_foreign_or_modified_asset_manifest_is_never_rendered():
    w,assets=sources()
    forged=deepcopy(assets)
    forged["world_digest"]="f"*64
    with pytest.raises(ExpeditionError,match="another source"):
        plan_game_lod(w,View(1,0,0,0),forged)
    forged=deepcopy(assets)
    forged["assets"].append(forged["assets"][0])
    with pytest.raises(ExpeditionError,match="ambiguous"):
        plan_game_lod(w,View(1,0,0,0),forged)


@pytest.mark.parametrize("field,value",(
    ("triangle_budget",0),("max_visible",0),
    ("near_m",0),("far_m",1),
))
def test_invalid_resource_budget_is_rejected(field,value):
    with pytest.raises(ExpeditionError):
        LODPolicy(**{field:value})


def test_frame_order_is_independent_of_unsorted_malformed_observations():
    w,assets=sources()
    with pytest.raises(ExpeditionError,match="increase"):
        render_lod_timeline(w,assets,[
            View(3,0,0,0),View(2,0,0,0),
        ])



def test_lod_manifest_cannot_spoof_a_different_mesh_path_or_checksum():
    w,assets=sources()
    tampered=deepcopy(assets)
    tampered["assets"][0]["mesh_path"]="../foreign.obj"
    from skeleton.jeeves.game_frontier_expedition import _digest
    tampered["receipt_digest"]=_digest({
        key:value for key,value in tampered.items() if key!="receipt_digest"
    })
    with pytest.raises(ExpeditionError,match="provenance path"):
        plan_game_lod(w,View(1,0,0,0),tampered)
    tampered=deepcopy(assets)
    tampered["assets"][0]["sha256"]="not-a-sha"
    tampered["receipt_digest"]=_digest({
        key:value for key,value in tampered.items() if key!="receipt_digest"
    })
    with pytest.raises(ExpeditionError,match="provenance path"):
        plan_game_lod(w,View(1,0,0,0),tampered)
