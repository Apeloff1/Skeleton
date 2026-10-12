"""Signed opt-in physics encounter rehearsal for original game-builder families.

This is actual executable physics built from the reviewed source of other
games, not a claim that those engines have already switched their authority.
Original game rules, session, money, NPC outcomes and source files stay
untouched; every encounter is independently replayed and content addressed.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)
from .advanced_level_scenes import (
    make_advanced_scene,validate_advanced_scene,
)
from .advanced_physics_runtime import default_layout as physics_layout
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.physics_interop_rehearsal.v1"
SUPPORTED=("platformer","racing","sandbox")
PHYSICAL_ACTIONS=frozenset((
    "inspect","step","step:4","push:east","push:west","push:up","push:down",
    "brake","torque:cw","torque:ccw",
))


class PhysicsInteropError(ValueError):
    """A source game or physical rehearsal failed its strict authority gate."""


def _digest(payload):
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _witnesses(source,original):
    editor=source["editor"]
    layout=original["layout"]
    state=source["state"]
    witnesses=[]
    if editor=="platformer":
        hazards=layout["hazards"]
        spawn,exit_x=layout["spawn_x"],layout["exit_x"]
        for x in hazards[:8]:
            # These are genuine original authored spikes, not fabricated hits.
            ratio=(x-spawn)*900//max(1,exit_x-spawn)
            witnesses.append({"source_type":"swept_platformer_spike",
                              "source_id":x,"x":350+ratio,"layer":3})
    elif editor=="racing":
        obstacle=layout["track_obstacle"]
        width=max(1,state["track_length"])
        x=420+min(650,obstacle*650//width)
        # Physical collision depends on the *replayed current lane*.
        # An avoided centerline obstacle is not silently declared a hit.
        witnesses.append({"source_type":"original_track_obstacle",
                          "source_id":obstacle,"x":x,
                          "layer":3 if state["lane"]==0 else 2})
    elif editor=="sandbox":
        for tile in layout["tiles"]:
            if tile["building"] is not None or tile["terrain"]=="ridge":
                witnesses.append({
                    "source_type":"authored_world_building"
                                  if tile["building"] is not None else "terrain_ridge",
                    "source_id":tile["id"],
                    "x":400+tile["id"]%8*120,
                    "layer":3 if tile["building"] not in ("road","bridge")
                              else 2,
                })
                if len(witnesses)>=8:
                    break
    return witnesses[:8]


def _physics_settings():
    return {
        "dimension":"2d","collision_geometry":"aabb","max_bodies":1,
        "substeps":1,"initial_battery":0,"gravity":0,"air_drag":0,
        "wall_restitution":0,"speed_limit":400,"impulse_strength":500,
        "completion_mode":"sandbox","goal_radius":25,
    }


def rehearse_physics_encounter(source_session, source_settings=None,
                               actions=("push:east",)*8):
    if type(source_session) is not dict or source_session.get("editor") not in SUPPORTED:
        raise PhysicsInteropError("source must be one of three approved original game families")
    if type(actions) not in (list,tuple) or not 1<=len(actions)<=32:
        raise PhysicsInteropError("finite physics rehearsal requires one to 32 commands")
    if any(type(action) is not str or action not in PHYSICAL_ACTIONS for action in actions):
        raise PhysicsInteropError("unreviewed physical command cannot enter cross-family rehearsal")
    editor=source_session["editor"]
    rules=make_editor_document(editor,source_settings)["settings"]
    try:
        verify_advanced_session(source_session,rules)
        if source_session["scene"] is None:
            raise PhysicsInteropError(
                "source must have a signed authored scene; generate and replay it first")
        original=validate_advanced_scene(source_session["scene"],rules)
        if original["editor"]!=editor or original["seed"]!=source_session["seed"]:
            raise PhysicsInteropError("original source identity mismatch")
        source_witnesses=_witnesses(source_session,original)
        settings=_physics_settings()
        cfg=make_editor_document("physics",settings)["settings"]
        layout=physics_layout(cfg,source_session["seed"])
        layout["fixtures"]=[]
        layout["goal"]=[1550,960,0]
        for witness in source_witnesses:
            layout["fixtures"].append({
                "position":[witness["x"],900,0],
                "half_size":[10,100,40],
                "layer":witness["layer"],
            })
        scene=make_advanced_scene(
            "physics",settings,seed=source_session["seed"],
            layout=layout,scene_id="interop_"+editor)
        result=run_advanced_session(
            "physics",settings,actions,seed=source_session["seed"],
            scene=scene)
        verify_advanced_session(result,settings)
    except PhysicsInteropError:
        raise
    except (ValueError,KeyError,TypeError) as exc:
        raise PhysicsInteropError("invalid original cross-family physical source or replay") from exc
    record={
        "schema":SCHEMA,"source_editor":editor,
        "source_scene_digest":original["digest"],
        "source_session_digest":source_session["digest"],
        "source_head_digest":source_session["head_digest"],
        "witnesses":source_witnesses,
        "physics_settings":settings,
        "physics_scene":scene,
        "physics_session":result,
        "observed_contacts":result["state"]["contacts"],
        "observed_impact":result["state"]["contacts"]>0,
        "native_hardware_verified":False,
        "source_gameplay_mutated":False,
        "automatic_promotion_allowed":False,
        "purpose":"read_only_interoperability_rehearsal",
    }
    return {**record,"digest":_digest(record)}


def verify_physics_encounter(proof,source_session,source_settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise PhysicsInteropError("signed interoperability proof schema required")
    if type(proof.get("physics_session")) is not dict:
        raise PhysicsInteropError("authored physics session missing from proof")
    actions=proof["physics_session"].get("actions")
    replay=rehearse_physics_encounter(source_session,source_settings,actions)
    if replay!=proof:
        raise PhysicsInteropError("cross-family source, physics, or evidence was modified")
    return True


__all__=["SCHEMA","SUPPORTED","PHYSICAL_ACTIONS","PhysicsInteropError",
         "rehearse_physics_encounter","verify_physics_encounter"]
