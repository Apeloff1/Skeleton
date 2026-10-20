"""Real source-bound seven-milestone game QA and tamper rejection."""
from copy import deepcopy
import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionError, ExpeditionWorld, TravelEdge, Waypoint,
)
from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile, author_archipelago
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_assets import forge_expedition_assets
from skeleton.jeeves.game_frontier_campaign_seven_audits import (
    AXES,audit_topology,audit_instruments,audit_objectives,audit_weather,
    audit_frames,audit_assets,compile_seven_campaign_audits,verify_seven_campaign_audits,
)


@pytest.fixture(scope="module")
def source():
    w=author_archipelago("audit_expedition","e"*64,
                         ArchipelagoProfile(seed=98,islands=5))
    p=original_campaign_player()
    return w,p,forge_expedition_assets(w)


def test_m1_original_directed_graph(source):
    w,_,_=source
    proof=audit_topology(w)
    assert proof["directed_edges"]==len(w.by_edge)
    assert proof["authored_links"]==len(w.edges)
    assert proof["world"]==w.digest
    assert not proof["unreachable_destinations"]


def test_m2_game_instruments_not_physical_gps(source):
    w,_,_=source
    report=audit_instruments(w)
    origin=next(v for v in report["observations"] if v["waypoint"]==w.arrival)
    assert origin["slant_range_m"]==0
    assert origin["sextant_elevation_degrees"]==0
    assert not report["physical_sensor_or_real_gps_verified"]
    with pytest.raises(ExpeditionError):
        audit_instruments(w,cap=1)


def test_m3_four_objectives_replay_gameplay(source):
    w,p,_=source
    report=audit_objectives(w,p)
    assert report["played_routes"]>=4
    assert report["pareto"]
    assert not report["native_game_executed"]


def test_m4_seven_environmental_permutations(source):
    w,p,_=source
    report=audit_weather(w,p)
    assert report["wins"]+report["blocked"]==7
    assert report["scenarios"][0]["won"]
    assert not report["environmental_sensor_evidence"]


def test_m5_frame_provenance_and_replay(source):
    w,p,_=source
    proof=audit_frames(w,p,subdivisions=4)
    assert proof["count"]>0
    assert proof["head"]==proof["frames"][-1]["receipt_digest"]
    assert not proof["native_rendered_frames_recorded"]
    assert audit_frames(w,p,subdivisions=4)==proof


def test_m6_real_mesh_byte_checks_and_coarse_draw_budget(source):
    w,_,assets=source
    report=audit_assets(w,assets)
    assert report["checked_objs"]==3*len(w.waypoints)
    assert report["low_detail_fits"]
    assert not report["native_gpu_profiled"]
    forged=deepcopy(assets)
    key=next(iter(forged["files"]))
    forged["files"][key]+="\nforged"
    with pytest.raises(ExpeditionError,match="digest"):
        audit_assets(w,forged)


def test_m7_delivery_review_is_source_bound_and_not_release_approval(source):
    w,p,assets=source
    report=compile_seven_campaign_audits(w,p,assets)
    assert set(report)==set(AXES)
    assert report["delivery"]["source_checks_passed"]
    assert not report["delivery"]["production_release_approved"]
    verify_seven_campaign_audits(w,p,assets,report)
    forged=deepcopy(report)
    forged["delivery"]["legal_review_signed"]=True
    with pytest.raises(ExpeditionError,match="forged"):
        verify_seven_campaign_audits(w,p,assets,forged)


def test_m7_rejects_foreign_assets(source):
    w,p,assets=source
    forged=deepcopy(assets)
    forged["manifest"]["world_digest"]="f"*64
    with pytest.raises(ExpeditionError,match="original world"):
        compile_seven_campaign_audits(w,p,forged)


def test_m1_parallel_edges_are_not_false_critical_choke_points():
    nodes=(
        Waypoint("entry",0,0,0,"settlement"),
        Waypoint("middle",10,0,0,"ground"),
        Waypoint("goal",20,0,0,"sky_island"),
    )
    links=(
        TravelEdge("parallel_a","entry","middle","walk",10,1,1),
        TravelEdge("parallel_b","entry","middle","walk",10,1,1),
        TravelEdge("final","middle","goal","walk",10,1,1),
    )
    world=ExpeditionWorld("parallel_graph","e"*64,nodes,links,"entry",("goal",))
    audit=audit_topology(world)
    assert audit["destination_cut_edges"]==["final"]
    assert not audit["unreachable_destinations"]
