"""Authenticated cross-genre motion acquisition into original physics exercises.

This is a real executable *handoff*, not a replacement for a genre's runtime:
every origin gameplay receipt is replayed independently, then a bounded
physics scene is derived from the verified source's last real positions,
velocity and authored obstacles. The derived game runs its own actual physics
and is replay-verified. No mutable client state becomes canonical training
evidence or silently alters the source game's rules.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping

from .advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from .advanced_level_scenes import make_advanced_scene
from .advanced_physics_runtime import default_layout
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.physics_cross_engine_handoff.v1"
ORIGINS=frozenset(("platformer","racing","flight","sailing"))
DOMAIN_SOURCE={
    "platformer":("hazards",3),
    "racing":("corners",8),
    "flight":("ridges",10),
    "sailing":("shoals",9),
}
FIXED_EXERCISE={
    "dimension":"2d","collision_geometry":"oriented_box",
    "max_bodies":1,"gravity":0,"initial_battery":0,
    "completion_mode":"sandbox",
}
OPTIONS=frozenset((
    "air_drag","floor_friction","contact_friction","wall_restitution",
    "impulse_strength","impulse_budget","oriented_sweep_budget",
    "broadphase_cell_size",
))
ACTION_LIMIT=24


class PhysicsHandoffError(ValueError):
    """A requested cross-engine physics exercise exceeds reviewed authority."""


def _digest(value):
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),
                   ensure_ascii=True,allow_nan=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _bounded(x,lo,hi):
    return max(lo,min(hi,x))


def _domain_projection(editor,session,source_settings,layout):
    state=session["state"]
    if editor=="platformer":
        x=state["x"];height=state["y"]
        vertical=-state["vy"]
        last=session["actions"][-1] if session["actions"] else "wait"
        vx=(-(source_settings["run_speed"]) if last in
            ("left","jump_left","dash_left") else
            source_settings["run_speed"] if last in
            ("right","jump_right","dash_right") else 0)
        if last.startswith("dash"):
            vx*=2
        return x,height,vx,vertical,0,"wood",3
    if editor=="racing":
        return (state["distance"],state["lane"]*35,
                state["speed"],0,state["lane"]*6000,"metal",10)
    if editor=="flight":
        return (state["x"],state["altitude"],
                state["speed"],-state["vertical_speed"],
                state["bank"]*15000,"metal",12)
    if editor=="sailing":
        return (state["x"],state["lane"]*35,
                state["speed"],0,state["heading"]*12000,
                "wood",9)
    raise PhysicsHandoffError("original gameplay engine has no reviewed physics acquisition")


def _source_obstacles(editor,layout):
    source_key,_=DOMAIN_SOURCE[editor]
    locations=[]
    for raw in layout[source_key][:4]:
        value=raw["x"] if type(raw) is dict else raw
        if type(value) is not int:
            raise PhysicsHandoffError("original source obstacle is not a bounded coordinate")
        locations.append(value)
    return locations


def run_physics_handoff(origin_session:dict,
                        origin_settings:Mapping[str,object]|None=None,
                        physics_actions=("inspect","step:4"),
                        physics_options:Mapping[str,object]|None=None)->dict:
    if type(origin_session) is not dict or origin_session.get("editor") not in ORIGINS:
        raise PhysicsHandoffError("only four source-replayed original motion engines are supported")
    editor=origin_session["editor"]
    if type(physics_actions) not in (tuple,list) or not 0<=len(physics_actions)<=ACTION_LIMIT:
        raise PhysicsHandoffError("physics acquisition actions exceed source budget")
    if type(physics_options) is not dict and physics_options is not None:
        raise PhysicsHandoffError("reviewed physics options must be exact mapping")
    options=dict(physics_options or {})
    if set(options)-OPTIONS:
        raise PhysicsHandoffError("handoff cannot change unreviewed physics settings or laws")
    origin_source=make_editor_document(editor,origin_settings)
    try:
        verify_advanced_session(origin_session,origin_source["settings"])
    except (AdvancedRuntimeError,TypeError,ValueError,KeyError) as exc:
        raise PhysicsHandoffError("origin must have intact canonical replay evidence") from exc
    source=(origin_session["scene"] if origin_session["scene"] is not None
            else make_advanced_scene(editor,origin_source["settings"],
                                     seed=origin_session["seed"]))
    fields=origin_source["settings"]
    layout=source["layout"]
    x,height,vx,vy,angle,material,mass=_domain_projection(
        editor,origin_session,fields,layout)
    policy={**FIXED_EXERCISE,**options}
    try:
        cfg=make_editor_document("physics",policy)
    except (ValueError,TypeError) as exc:
        raise PhysicsHandoffError("invalid bounded physics exercise settings") from exc
    stage=default_layout(cfg["settings"],origin_session["seed"])
    body=stage["bodies"][0]
    body["position"]=[
        _bounded(200+abs(x)%240,100,440),
        _bounded(960-abs(height)%700,60,960),0]
    body["velocity"]=[
        _bounded(vx,-cfg["settings"]["speed_limit"],cfg["settings"]["speed_limit"]),
        _bounded(vy,-cfg["settings"]["speed_limit"],cfg["settings"]["speed_limit"]),0]
    body["material"]=material
    body["mass"]=mass
    body["shape_half"]=[35,16] if editor in ("racing","sailing") else [30,24]
    body["initial_orientation"]=angle%360000
    stage["fixtures"]=[]
    obstacles=_source_obstacles(editor,layout)
    for index,item in enumerate(obstacles):
        # These are explicitly derived *new* physics course obstacles,
        # not falsely claimed exact geometry parity with source genre.
        px=590+(abs(item)%7)*120
        stage["fixtures"].append({
            "position":[px,850-index*80,0],
            "half_size":[20,40,30],
            "layer":3,
            "orientation":(abs(item)%4)*15000,
        })
    stage["goal"]=[1000,960,0]
    physics_scene=make_advanced_scene(
        "physics",cfg["settings"],seed=origin_session["seed"],layout=stage)
    try:
        exercise=run_advanced_session(
            "physics",cfg["settings"],physics_actions,
            seed=origin_session["seed"],scene=physics_scene)
        verify_advanced_session(exercise,cfg["settings"])
    except (AdvancedRuntimeError,ValueError,KeyError) as exc:
        raise PhysicsHandoffError("source-derived physical exercise did not execute") from exc
    # Provenance is immutable evidence. Source gameplay state is not modified.
    report={
        "schema":SCHEMA,"quality_floor":"advanced",
        "origin_editor":editor,
        "origin_session":origin_session,
        "origin_settings":fields,
        "origin_session_digest":origin_session["digest"],
        "origin_scene_digest":origin_session["scene_digest"],
        "origin_turns":len(origin_session["trace"]),
        "derived_obstacle_count":len(stage["fixtures"]),
        "physics_settings":cfg["settings"],
        "physics_scene":physics_scene,
        "physics_session":exercise,
        "physics_actions":list(physics_actions),
        "origin_state_fingerprint":_digest({
            "x":x,"height":height,"vx":vx,"vy":vy,
            "angle":angle,"material":material,"mass":mass,
        }),
        "policy":"derived_training_exercise_not_live_genre_override",
        "native_parity_verified":False,
        "training_weights_promoted":False,
    }
    return {**report,"digest":_digest(report)}


def verify_physics_handoff(evidence:dict)->bool:
    if type(evidence) is not dict or evidence.get("schema")!=SCHEMA:
        raise PhysicsHandoffError("source-bound physics handoff schema required")
    required={
        "schema","quality_floor","origin_editor","origin_session",
        "origin_settings","origin_session_digest","origin_scene_digest",
        "origin_turns","derived_obstacle_count","physics_settings",
        "physics_scene","physics_session","physics_actions",
        "origin_state_fingerprint","policy","native_parity_verified",
        "training_weights_promoted","digest",
    }
    if set(evidence)!=required:
        raise PhysicsHandoffError("physics acquisition cannot contain unreviewed state")
    if type(evidence["physics_settings"]) is not dict:
        raise PhysicsHandoffError("reviewed physics settings must be an exact mapping")
    policy={key:value for key,value in evidence["physics_settings"].items()
            if key in OPTIONS}
    actual=run_physics_handoff(evidence["origin_session"],
             evidence["origin_settings"],evidence["physics_actions"],policy)
    if actual!=evidence:
        raise PhysicsHandoffError("cross-engine source, dynamics, or evidence was tampered")
    return True


__all__=["SCHEMA","ORIGINS","PhysicsHandoffError",
         "run_physics_handoff","verify_physics_handoff"]
