"""Advanced original game milestones: real math, cargo, authored visuals and replay."""
from copy import deepcopy
from dataclasses import replace
from base64 import b64encode
from hashlib import sha256
import json
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError,_digest
from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile,author_archipelago
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_animation import original_actor_rig
from skeleton.jeeves.game_frontier_expedition_npcs import original_world_npcs
from skeleton.jeeves.game_frontier_expedition_cinematics import original_game_storyboard
from skeleton.jeeves.game_frontier_ik import LimbTarget,solve_limb_ik,solve_foot_plant
from skeleton.jeeves.game_frontier_ragdoll import RagdollPolicy,simulate_ragdoll,verify_ragdoll
from skeleton.jeeves.game_frontier_supply import Recipe,SupplyNetwork,original_supply_network
from skeleton.jeeves.game_frontier_blocking import (
    BlockingKey,ActorTrack,track_at,author_original_blocking,export_blocking_godot,
)
from skeleton.jeeves.game_frontier_visual_capture import (
    PREFIX,ingest_godot_viewport_log,export_native_capture_godot,
)
from skeleton.jeeves.game_frontier_expedition_visual_lab import original_procedural_preview_frames
from skeleton.jeeves.game_frontier_controller_parity import (
    GameIntent,replay_profile_intents,verify_all_controller_eras,
)
from skeleton.jeeves.game_frontier_expedition_controllers import (
    controller_profiles,profile_for,
)
from skeleton.jeeves.game_frontier_soak import (
    ProcessCycle,verify_process_cycles,simulated_process_recovery,
)

def game(seed=21):
    return author_archipelago("advanced_game","f"*64,
                              ArchipelagoProfile(seed=seed,islands=5))

def test_original_ik_solves_reachable_limb_and_bounded_foot_contact():
    w=game()
    rig,_=original_actor_rig(w.digest)
    # A game actor gains only a typed original virtual forearm child.
    from skeleton.jeeves.game_frontier_expedition_animation import Rig,Bone
    r=Rig(w.digest,rig.actor_id,rig.bones+(Bone("forearm","left_arm",.45,1.5,170),))
    target=LimbTarget(r.actor_id,"left_arm","forearm",0,0,.95,.2)
    proof=solve_limb_ik(r,target)
    assert proof["world"]==w.digest
    assert proof["error_m"]<1e-6
    assert not proof["native_ik_verified"]
    assert len(proof["receipt_digest"])==64
    feet=solve_foot_plant(rig,frame=18)
    assert len(feet["feet"])==2
    assert all(item["error_m"]<.001 for item in feet["feet"].values())

def test_original_ik_rejects_unreachable_targets_foreign_rig_and_nonfinite_positions():
    w=game()
    rig,_=original_actor_rig(w.digest)
    from skeleton.jeeves.game_frontier_expedition_animation import Rig,Bone
    rig=Rig(w.digest,rig.actor_id,rig.bones+(Bone("shin","left_leg",.5,2,170),))
    with pytest.raises(ExpeditionError,match="unreachable"):
        solve_limb_ik(rig,LimbTarget(rig.actor_id,"left_leg","shin",0,0,100,0))
    with pytest.raises(ExpeditionError,match="authoritative"):
        solve_limb_ik(rig,LimbTarget("foreign_actor","left_leg","shin",0,0,1,0))
    with pytest.raises(ExpeditionError,match="finite"):
        LimbTarget(rig.actor_id,"left_leg","shin",0,float("nan"),0,0)

def test_ragdoll_replays_real_bone_chain_without_floor_tunneling():
    rig,_=original_actor_rig(game().digest)
    proof=simulate_ragdoll(rig,frames=24)
    assert proof["frames"]==24
    assert len(proof["states"])==24
    assert all(y>=0 for row in proof["states"] for _,y in row["positions"])
    assert proof["receipt_head"]==proof["states"][-1]["receipt_digest"]
    assert not proof["native_rigid_body_validated"]
    verify_ragdoll(rig,proof,frames=24)

def test_ragdoll_nonfinite_gravity_and_forged_trajectory_are_rejected():
    rig,_=original_actor_rig(game().digest)
    with pytest.raises(ExpeditionError,match="nonfinite"):
        RagdollPolicy(gravity=float("nan"))
    p=simulate_ragdoll(rig,frames=5)
    p["states"][1]["positions"][1][1]=300
    with pytest.raises(ExpeditionError,match="do not reproduce"):
        verify_ragdoll(rig,p,frames=5)

def test_npc_supply_chain_spends_inputs_conserves_coins_and_restores():
    w=game()
    cast=original_world_npcs(w)
    result=original_supply_network(w,cast)
    assert result["world"]==w.digest
    assert sum(result["coins"].values())+result["treasury"]==600
    assert result["stock"][cast[1].npc_id]["tools"]==1
    assert SupplyNetwork.restore(
        w,cast,(Recipe("forge_tools",(("ore",2),("fiber",1)),"tools",1,2),
                Recipe("sew_gliders",(("fiber",3),),"glider_cloth",1,1)),result,
    ).snapshot()==result

def test_supply_ledger_rejects_double_spend_and_modified_cargo_history():
    w=game()
    cast=original_world_npcs(w)
    recipe=Recipe("forge_tools",(("ore",2),("fiber",1)),"tools",1)
    net=SupplyNetwork(w,cast,(recipe,))
    with pytest.raises(ExpeditionError,match="double-spend"):
        net.execute("transfer",actor=cast[0].npc_id,target=cast[1].npc_id,
                    item="tools")
    net.execute("craft",actor=cast[0].npc_id,recipe="forge_tools")
    altered=deepcopy(net.snapshot())
    altered["stock"][cast[0].npc_id]["tools"]=99
    altered["snapshot_digest"]=_digest({
        key:value for key,value in altered.items() if key!="snapshot_digest"
    })
    with pytest.raises(ExpeditionError,match="disagrees"):
        SupplyNetwork.restore(w,cast,(recipe,),altered)

def test_actor_blocking_replays_source_camera_with_nonoverlapping_original_cast():
    w=game()
    board=original_game_storyboard(w,"c"*64)
    cast=original_world_npcs(w)
    result=author_original_blocking(w,board,cast)
    assert len(result["tracks"])==9
    assert result["sample_frames"]
    assert all(len(x["actors"])==3 for x in result["sample_frames"])
    assert result==author_original_blocking(w,board,cast)
    assert len(result["receipt_digest"])==64
    scripts=export_blocking_godot(w,board,cast)
    assert "game/frontier/actor_blocking.gd" in scripts
    assert "EXPEDITION_BLOCKING_READY" in scripts["game/frontier/actor_blocking.gd"]

def test_actor_blocking_rejects_unordered_or_missing_keyframes():
    from skeleton.jeeves.game_frontier_blocking import BlockingKey,ActorTrack
    a=BlockingKey(2,"actor",0,0,0)
    b=BlockingKey(1,"actor",1,0,0)
    with pytest.raises(ExpeditionError,match="chronology"):
        ActorTrack("shot","actor",(a,b))

def viewport_log(world):
    rows=[]
    frames=original_procedural_preview_frames(world,frames=2,width=8,height=8)
    for f in frames:
        rows.append(PREFIX+json.dumps({
            "world_digest":world,"frame":f.frame,"width":f.width,
            "height":f.height,"kind":"original_runtime_capture",
            "pixel_sha256":sha256(f.rgb).hexdigest(),
            "rgb_base64":b64encode(f.rgb).decode("ascii"),
        }))
    return "\n".join(rows)

def test_dragon_ingests_exact_pixel_arrays_and_labels_unattested_native_origin():
    w=game()
    proof=ingest_godot_viewport_log(viewport_log(w.digest),expected_world=w.digest)
    assert len(proof["frames"])==2
    assert proof["comparison"]["frame_count"]==2
    assert not proof["report"]["native_runner_attestation_verified"]
    assert "game/frontier/viewport_capture.gd" in export_native_capture_godot()

def test_dragon_capture_rejects_corrupted_pixel_hash_and_foreign_world():
    w=game()
    original=viewport_log(w.digest)
    with pytest.raises(ExpeditionError,match="checksum"):
        ingest_godot_viewport_log(original.replace('"pixel_sha256": "', '"pixel_sha256": "f',1),
                                  expected_world=w.digest)
    with pytest.raises(ExpeditionError,match="foreign"):
        ingest_godot_viewport_log(original,expected_world="e"*64)

def test_controller_parity_executes_all_seven_era_layouts():
    result=verify_all_controller_eras(game().digest)
    assert result["profile_count"]==7
    assert all(x["accepted_actions"]==6 for x in result["profiles"])
    assert all(not x["native_usb_parity_proven"] for x in result["profiles"])
    assert not result["hardware_parity_validated"]

def test_controller_parity_detects_unbound_intent_and_repeated_frames():
    p=profile_for("four_button")
    with pytest.raises(ExpeditionError,match="monotonically"):
        replay_profile_intents(p,(GameIntent(2,"travel"),GameIntent(2,"rest")),
                               world_digest=game().digest)
    assert len(controller_profiles())==7

def test_soak_lifecycle_rejects_unmeasured_uptime_and_broken_restart_linkage():
    w=game()
    proof=simulated_process_recovery(w.digest)
    assert proof["cycles"]==6
    assert not proof["measured_uptime_qualified"]
    assert proof["measured_months"]==0
    first=ProcessCycle(1,0,100,"a"*64,"b"*64,0,False)
    second=ProcessCycle(2,101,201,"c"*64,"d"*64,0,True)
    with pytest.raises(ExpeditionError,match="missing/altered"):
        verify_process_cycles(w.digest,(first,second))
    with pytest.raises(ExpeditionError,match="synthetic"):
        verify_process_cycles(w.digest,(first,replace(second,before_receipt="b"*64)),
                              require_measured=True)

def test_host_reported_process_intervals_are_monetized_only_as_measured_seconds():
    w=game()
    a=ProcessCycle(1,0,1_000_000_000,"0"*64,"1"*64,0,False,True)
    b=ProcessCycle(2,1_000_000_000,3_000_000_000,"1"*64,"2"*64,0,True,True)
    report=verify_process_cycles(w.digest,(a,b),require_measured=True,min_measured_seconds=3)
    assert report["measured_uptime_qualified"]
    assert report["duration_seconds"]==3
    assert 0<report["measured_months"]<.001
    assert not report["release_approved"]
