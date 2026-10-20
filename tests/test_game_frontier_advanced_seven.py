"""Seven instrumental game systems: actual replay, numeric boundaries, provenance."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_npcs import original_world_npcs
from skeleton.jeeves.game_frontier_expedition_narrative import original_expedition_story
from skeleton.jeeves.game_frontier_expedition_cinematics import original_game_storyboard
from skeleton.jeeves.game_frontier_expedition_controllers import profile_for
from skeleton.jeeves.game_frontier_expedition_animation import (
    Bone,Rig,AnimationClip,PoseKey,SkinPolicy,original_actor_rig,
    sample_pose,blend_poses,simulate_elastic_skin,export_actor_rig_godot,
)
from skeleton.jeeves.game_frontier_expedition_society import (
    SocietyPolicy,SocialActor,Society,original_society,simulate_original_society,
)
from skeleton.jeeves.game_frontier_expedition_performance import (
    PerformancePolicy,author_performance,verify_performance,export_performance_godot,
)
from skeleton.jeeves.game_frontier_expedition_visual_lab import (
    VisualFrame,original_procedural_preview_frames,compare_original_visuals,
    verify_visual_comparison,
)
from skeleton.jeeves.game_frontier_expedition_controller_latency import (
    InputObservation,simulated_controller_trace,qualify_game_controller,
    verify_game_controller,
)
from skeleton.jeeves.game_frontier_expedition_watchdog import (
    ProductionBudget,ResourceSample,ProductionWatchdog,simulate_production_health,
)
from skeleton.jeeves.game_frontier_expedition_seven_review import (
    objectively_review_seven_planes,verify_seven_planes,
)
from skeleton.jeeves.game_frontier_expedition import _digest


def game(seed=11):
    return author_archipelago("seven_advanced","a"*64,
                              ArchipelagoProfile(seed=seed,islands=5))


def test_actual_joint_hierarchy_pose_blend_and_soft_skin_is_replayable():
    w=game()
    rig,clip=original_actor_rig(w.digest)
    assert rig.digest==clip.rig_digest
    pose_a=sample_pose(rig,clip,0)
    pose_b=sample_pose(rig,clip,30)
    blended=blend_poses(rig,pose_a,pose_b,.5)
    assert blended["angles"][3]==0
    assert sample_pose(rig,clip,15)["frame"]==15
    skin=simulate_elastic_skin(rig,clip,frames=48)
    assert skin["frames"]==48
    assert skin["head"]==skin["samples"][-1]["receipt_digest"]
    assert all(abs(x)<=SkinPolicy().max_offset_m for row in skin["samples"]
               for x in row["skin_offsets"])
    assert skin==simulate_elastic_skin(rig,clip,frames=48)
    assert not skin["native_soft_tissue_validated"]


def test_rig_rejects_disconnected_bones_and_foreign_animation():
    w=game()
    rig,clip=original_actor_rig(w.digest)
    with pytest.raises(ExpeditionError,match="precede"):
        Rig(w.digest,"bad",(
            Bone("child","unseen",.2,1),
            Bone("root","",.5,2),
        ))
    with pytest.raises(ExpeditionError,match="another skeleton"):
        sample_pose(original_actor_rig(game(seed=13).digest)[0],clip,0)
    with pytest.raises(ExpeditionError,match="rotation limit"):
        bad=AnimationClip("twist",rig.digest,2,(
            PoseKey(0,(0,0,0,99,0,0,0)),
            PoseKey(1,(0,0,0,99,0,0,0)),
        ))
        sample_pose(rig,bad,0)


def test_original_godot_joint_rig_is_real_executable_source():
    rig,clip=original_actor_rig(game().digest)
    output=export_actor_rig_godot(rig,clip)
    assert "game/frontier/actor_rig.json" in output
    assert "Node3D.new()" in output["game/frontier/actor_rig.gd"]
    assert "rotation_degrees.z" in output["game/frontier/actor_rig.gd"]


def test_npc_society_replays_conserved_goods_and_coins_with_faction_propagation():
    w=game()
    society=original_society(w,original_world_npcs(w))
    before=sum(society.coins.values())
    assert society.tick(1,actor_id=society.actors[0].npc_id,kind="work")["produced"]==2
    society.tick(2,actor_id=society.actors[0].npc_id,
                 kind="trade",target=society.actors[1].npc_id)
    society.tick(3,actor_id=society.actors[0].npc_id,
                 kind="praise",conduct=16)
    assert sum(society.coins.values())==before
    assert sum(society.goods.values())==2
    assert society.standing[society.actors[0].npc_id]==16
    assert Society.restore(w,society.actors,society.snapshot()).snapshot()==society.snapshot()
    assert simulate_original_society(w,original_world_npcs(w))["world"]==w.digest


def test_society_fails_closed_on_inflation_missing_stock_and_modified_history():
    w=game()
    society=original_society(w,original_world_npcs(w))
    with pytest.raises(ExpeditionError,match="cannot create"):
        society.tick(1,actor_id=society.actors[0].npc_id,
                     kind="trade",target=society.actors[1].npc_id)
    society.tick(1,actor_id=society.actors[0].npc_id,kind="work")
    modified=deepcopy(society.snapshot())
    modified["coins"][society.actors[0].npc_id]+=100
    modified["snapshot_digest"]=_digest({
        k:v for k,v in modified.items() if k!="snapshot_digest"
    })
    with pytest.raises(ExpeditionError,match="replay failed|disagreed"):
        Society.restore(w,society.actors,modified)


def test_original_cinematic_performance_has_exact_source_dialogue_and_visemes():
    w=game()
    story=original_expedition_story(w,"a"*64)
    board=original_game_storyboard(w,"a"*64)
    performance=author_performance(story,board)
    assert len(performance["takes"])==3
    assert all(x["visemes"] for x in performance["takes"])
    assert all(x["speaker"] in ("harbor_keeper","cloud_witness","sky_archivist")
               for x in performance["takes"])
    assert not performance["native_character_animation_verified"]
    verify_performance(story,board,performance)
    source=export_performance_godot(story,board)
    assert "MeshInstance3D.new()" in source["game/frontier/performance.gd"]


def test_lipsync_cannot_use_mismatched_gdd_or_story_text():
    w=game()
    a=original_expedition_story(w,"a"*64)
    b=original_game_storyboard(w,"b"*64)
    with pytest.raises(ExpeditionError,match="one original GDD"):
        author_performance(a,b)
    legit=author_performance(a,original_game_storyboard(w,"a"*64))
    forged=deepcopy(legit)
    forged["takes"][0]["dialogue"]="unreviewed"
    with pytest.raises(ExpeditionError,match="differ"):
        verify_performance(a,original_game_storyboard(w,"a"*64),forged)


def test_dragon_rgb_lab_measures_real_supplied_pixels_not_fake_video():
    a=game()
    b=game(seed=17)
    frames_a=original_procedural_preview_frames(a.digest)
    frames_b=original_procedural_preview_frames(b.digest,seed=71)
    report=compare_original_visuals((frames_a,frames_b))
    assert report["frame_count"]==8
    assert len(report["games"])==2
    assert all(x["average_motion_delta"]>0 for x in report["games"])
    assert not report["neural_weights_promoted"]
    assert not report["real_video_source_inferred"]
    verify_visual_comparison((frames_a,frames_b),report)


def test_dragon_visual_evidence_tamper_crossworld_and_reverse_frames_are_rejected():
    a=game()
    b=game(seed=13)
    frames=original_procedural_preview_frames(a.digest)
    report=compare_original_visuals((frames,))
    report["games"][0]["average_motion_delta"]=0
    with pytest.raises(ExpeditionError,match="differ"):
        verify_visual_comparison((frames,),report)
    with pytest.raises(ExpeditionError,match="game source"):
        compare_original_visuals(((frames[0],
                                   original_procedural_preview_frames(b.digest)[1]),))
    with pytest.raises(ExpeditionError,match="frame order"):
        compare_original_visuals(((frames[1],frames[0]),))


def test_controller_latency_fixture_is_evidence_only_not_hardware_claim():
    p=profile_for("dual_stick")
    source=simulated_controller_trace(p,count=12)
    checked=qualify_game_controller(p,source,world_digest=game().digest)
    assert checked["latency_budget_met"]
    assert checked["latency"]["max_us"]>checked["latency"]["min_us"]
    assert checked["observed_events"]==12
    assert not checked["full_hardware_qualification"]
    verify_game_controller(p,source,checked,world_digest=game().digest)
    with pytest.raises(ExpeditionError,match="cannot use simulated"):
        qualify_game_controller(p,source,world_digest=game().digest,
                                requires_hardware=True)


def test_controller_trace_fails_on_missing_events_or_clock_reversal():
    p=profile_for("four_button")
    source=simulated_controller_trace(p,count=4)
    with pytest.raises(ExpeditionError,match="missing or reordered"):
        qualify_game_controller(p,(source[0],source[2]),world_digest=game().digest)
    with pytest.raises(ExpeditionError,match="timestamps"):
        InputObservation(1,1,"travel",2000,1500,3000)


def test_watchdog_detects_overmemory_disk_pressure_and_stall():
    w=game()
    monitor=ProductionWatchdog(w.digest,ProductionBudget(max_no_progress_ticks=2))
    head="e"*64
    first=monitor.observe(ResourceSample(1,100,20,5000,head))
    second=monitor.observe(ResourceSample(2,100,20,5000,head))
    third=monitor.observe(ResourceSample(3,100,20,5000,head))
    assert third["violations"]==["stalled"]
    assert monitor.halted
    assert ProductionWatchdog.restore(w.digest,monitor.snapshot()).snapshot()==monitor.snapshot()
    with pytest.raises(ExpeditionError,match="halted"):
        monitor.observe(ResourceSample(4,100,20,5000,head))
    memory=ProductionWatchdog(w.digest)
    assert memory.observe(ResourceSample(1,99999,10,0,"f"*64))["violations"]==["memory","disk"]


def test_watchdog_chain_rejects_modified_resources_and_measured_uptime_claims():
    w=game()
    original=simulate_production_health(w.digest,ticks=12)
    assert original["actual_months_observed"]==0
    assert not original["halted"]
    altered=deepcopy(original)
    altered["history"][0]["observation"]["rss_mb"]=100000
    altered["snapshot_digest"]=_digest({
        k:v for k,v in altered.items() if k!="snapshot_digest"
    })
    with pytest.raises(ExpeditionError,match="differ|halted"):
        ProductionWatchdog.restore(w.digest,altered)


def _assurance_fixture():
    w=game()
    rig,clip=original_actor_rig(w.digest)
    elastic=simulate_elastic_skin(rig,clip,frames=12)
    society=simulate_original_society(w,original_world_npcs(w))
    story=original_expedition_story(w,"a"*64)
    board=original_game_storyboard(w,"a"*64)
    perf=author_performance(story,board)
    vision=compare_original_visuals((original_procedural_preview_frames(w.digest),))
    controller=profile_for("dual_stick")
    latency=qualify_game_controller(controller,simulated_controller_trace(controller),
                                  world_digest=w.digest)
    watch=simulate_production_health(w.digest,ticks=12)
    return w,{
        "rig":{"rig_digest":rig.digest,"soft_body_receipt":elastic["receipt_digest"],
               "world":w.digest},
        "society":society,"performance":perf,
        "dragon_vision":vision,"controller_latency":latency,
        "production_watchdog":watch,
        "rights_and_native":{
            "rights_signed":False,"native_game_executed":False,
            "physical_controller_verified":False,"long_duration_days":0,
            "world":w.digest,
        },
    }


def test_seven_plane_release_review_stays_blocked_when_legal_and_hardware_absent():
    w,artifacts=_assurance_fixture()
    receipt=objectively_review_seven_planes(w.digest,artifacts)
    assert receipt["total"]==7
    assert receipt["passed"]==6
    assert not receipt["production_release_approved"]
    assert not receipt["publication_authorized"]
    assert len(receipt["unresolved_gaps"])==4
    verify_seven_planes(w.digest,artifacts,receipt)


def test_seven_plane_report_cannot_silently_claim_unsigned_release():
    w,artifacts=_assurance_fixture()
    forged=objectively_review_seven_planes(w.digest,artifacts)
    forged["production_release_approved"]=True
    with pytest.raises(ExpeditionError,match="differ"):
        verify_seven_planes(w.digest,artifacts,forged)
    artifacts["rig"]["world"]="f"*64
    with pytest.raises(ExpeditionError,match="different world"):
        objectively_review_seven_planes(w.digest,artifacts)
