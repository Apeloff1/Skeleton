"""Differentially prove approved wind-dash player input changed native Godot physics.

The control and explicitly opt-in headless playthrough must share exactly the
same scene, actor and starting physics state. This is bounded local gameplay,
not a signed operator identity or canonical game-world modification.
"""
from __future__ import annotations
from hashlib import sha256
import json
from math import isclose, isfinite, sqrt

from .game_frontier_native_quest_session import NativeQuestSessionError


def _sha(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def _vector(value):
    if (type(value) is not list or len(value)!=3
        or any(type(v) not in (float,int) or not isfinite(v) for v in value)):
        raise NativeQuestSessionError("wind dash evidence requires finite 3D vector")
    return [float(v) for v in value]


def _close(a,b, tolerance=1e-4):
    return all(isclose(x,y,abs_tol=tolerance,rel_tol=0)
               for x,y in zip(_vector(a),_vector(b)))


def _read_actor_rows(lines,*,actor,scene,gdd,fps):
    frames=[]
    if type(lines) is not list or not 4<=len(lines)<=128:
        raise NativeQuestSessionError("bounded complete Godot dash playthrough required")
    for i,line in enumerate(lines):
        if type(line) is not dict or (
            line.get("schema")!="skeleton.game.native_physics_observation.v1"
            or line.get("authority")!="untrusted_native_candidate_observation_not_attested"
            or line.get("native_engine")!="godot4_physics"
            or line.get("scene_candidate_digest")!=scene
            or line.get("signed_gdd_digest")!=gdd
            or type(line.get("native_tick")) is not int
            or line["native_tick"]!=i
            or type(line.get("fps")) is not int
            or line["fps"]!=fps):
            raise NativeQuestSessionError("Godot dash observation source/frame mismatch")
        actors=line.get("actors")
        if type(actors) is not list:
            raise NativeQuestSessionError("typed engine actors missing")
        chosen=[a for a in actors if type(a) is dict and a.get("id")==actor]
        if len(chosen)!=1:
            raise NativeQuestSessionError("controlled game actor missing or duplicated")
        row=chosen[0]
        physics=row.get("physics_body")
        if (type(physics) is not dict or physics.get("mode")!="rigid"
            or type(physics.get("mass_kg")) not in (float,int)
            or not isfinite(physics["mass_kg"]) or physics["mass_kg"]<=0):
            raise NativeQuestSessionError("native dash requires genuine rigid physics body")
        _vector(row.get("world_xyz_m"))
        _vector(row.get("velocity_xyz_mps"))
        frames.append(row)
    return frames


def verify_native_wind_dash_playthrough(
    control: list, activated: list, activation: object, dispatch: object,
    *, fps: int,
) -> dict:
    if (type(dispatch) is not dict
        or dispatch.get("schema")!="skeleton.game.native_godot_dispatch.v1"
        or type(fps) is not int or fps not in (30,50,60,120)
        or type(activation) is not dict):
        raise NativeQuestSessionError("signed-source bounded dash input audit required")
    actor=dispatch.get("actor_id")
    scene=dispatch.get("scene_candidate_digest")
    gdd=dispatch.get("signed_gdd_digest")
    skill=dispatch.get("expected_unlocked_skills")
    level=dispatch.get("expected_local_level")
    source_receipt=dispatch.get("receipt_digest")
    if (type(actor) is not str or not actor
        or type(scene) is not str or len(scene)!=64
        or type(gdd) is not str or len(gdd)!=64
        or type(source_receipt) is not str or len(source_receipt)!=64
        or type(level) is not int or not 1<=level<=100
        or type(skill) is not dict or type(skill.get("wind_dash")) is not int
        or skill["wind_dash"]>level):
        raise NativeQuestSessionError("dash not unlocked by approved source gameplay")
    before=_read_actor_rows(control,actor=actor,scene=scene,gdd=gdd,fps=fps)
    after=_read_actor_rows(activated,actor=actor,scene=scene,gdd=gdd,fps=fps)
    if len(before)!=len(after):
        raise NativeQuestSessionError("control and wind-dash runs have different frame coverage")
    keys={
        "schema","actor_id","scene_candidate_digest","signed_gdd_digest",
        "approved_dispatch_digest","skill","skill_required_level",
        "current_level","source_game_tick","bounded_impulse_ns",
        "player_mass_kg","impulse_world_xyz_ns","velocity_before_world_xyz_mps",
        "input_mode","authority",
    }
    if (set(activation)!=keys
        or activation["schema"]!="skeleton.game.approved_local_wind_dash_activation.v1"
        or activation["authority"]!="local_player_control_not_canonical_world_edit"
        or activation["input_mode"]!="explicit_native_ci"
        or activation["actor_id"]!=actor
        or activation["scene_candidate_digest"]!=scene
        or activation["signed_gdd_digest"]!=gdd
        or activation["approved_dispatch_digest"]!=source_receipt
        or activation["skill"]!="wind_dash"
        or type(activation["skill_required_level"]) is not int
        or activation["skill_required_level"]!=skill["wind_dash"]
        or type(activation["current_level"]) is not int
        or activation["current_level"]!=level
        or type(activation["source_game_tick"]) is not int
        or activation["source_game_tick"]!=2):
        raise NativeQuestSessionError("dash receipt is not source-approved controlled fixture")
    impulse=_vector(activation["impulse_world_xyz_ns"])
    prior=_vector(activation["velocity_before_world_xyz_mps"])
    mass=activation["player_mass_kg"]
    cap=activation["bounded_impulse_ns"]
    if (type(mass) not in (int,float) or not isfinite(mass) or mass<=0
        or type(cap) not in (int,float) or not isfinite(cap)
        or not isclose(cap,min(45.,mass*3.),abs_tol=1e-5)
        or not isclose(mass,after[1]["physics_body"]["mass_kg"],abs_tol=1e-5)
        or not isclose(sqrt(sum(x*x for x in impulse)),cap,abs_tol=1e-4)
        or abs(impulse[2])>1e-5):
        raise NativeQuestSessionError("wind dash impulse and source body mass are invalid")
    # Strict control equivalence before the scheduled source-approved impulse.
    for i in (0,1):
        if (not _close(before[i]["world_xyz_m"],after[i]["world_xyz_m"])
            or not _close(before[i]["velocity_xyz_mps"],after[i]["velocity_xyz_mps"])):
            raise NativeQuestSessionError("comparison physics diverged before approved action")
    if not _close(prior,after[1]["velocity_xyz_mps"]):
        raise NativeQuestSessionError("claimed wind dash prior velocity does not match engine")
    # A true physics impulse must produce measurable additional speed along
    # the applied vector at the following solver sample.
    direction=[c/cap for c in impulse]
    observed=[]
    for i in range(2,len(before)):
        av=_vector(after[i]["velocity_xyz_mps"])
        bv=_vector(before[i]["velocity_xyz_mps"])
        observed.append(sum((a-b)*d for a,b,d in zip(av,bv,direction)))
    if max(observed)<0.12:
        raise NativeQuestSessionError("wind dash did not measurably change real Godot velocity")
    report={
        "schema":"skeleton.game.native_wind_dash_differential.v1",
        "source_dispatch_digest":source_receipt,
        "scene_candidate_digest":scene,"signed_gdd_digest":gdd,
        "actor_id":actor,"fps":fps,"frame_count":len(before),
        "activation_tick":activation["source_game_tick"],
        "approved_skill_level":skill["wind_dash"],
        "impulse_magnitude_ns":cap,
        "peak_added_velocity_along_impulse_mps":max(observed),
        "control_capture_digest":_sha(control),
        "activated_capture_digest":_sha(activated),
        "activation_digest":_sha(activation),
        "authority":"measured_differential_native_physics_not_production_user_authentication",
    }
    report["receipt_digest"]=_sha(report)
    return report
