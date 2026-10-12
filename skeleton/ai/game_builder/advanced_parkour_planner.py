"""Bounded AI-facing course planner using the real original parkour engine.

All successors are produced by trusted integer gameplay transitions; no map
teleport, fabricated medal or client state is accepted. Only an independently
replayed actual finished game may become a verified route. The beam is not an
exhaustive solver: budget exhaustion and no candidate never mean impossible.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    MAX_TURNS, run_advanced_session, verify_advanced_session,
)
from .advanced_level_scenes import validate_advanced_scene
from .advanced_parkour_runtime import (
    ParkourActionError, start, step, apply_scene,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.parkour_route_plan.v1"
PLANNER_ACTIONS=(
    "run","sprint","jump","double_jump","vault","slide","wall_run","grapple",
    "swing","climb","mantle","roll","lane_left","lane_right","recover","rest",
)
DEFAULT_MAX_STATES=12000
DEFAULT_BEAM_WIDTH=90


class ParkourPlanningError(ValueError):
    """Invalid planning budget or untrusted source rather than an impossible game."""


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _signature(s):
    """Only authoritative physical state; event messages are not search authority."""
    return (
        s["x"],s["lane"],s["height"],s["vertical_speed"],s["momentum"],
        s["stamina"],s["health"],s["grip"],s["grapple_charges"],
        s["wall_run_remaining"],s["cooldown"],s["checkpoint"],
        s["checkpoint_lane"],tuple(s["medals_collected"]),
        s["falls"],s["tick"]%4,
    )


def _priority(s,actions):
    return (
        len(s["medals_collected"])*10000+s["x"]*100+s["health"]*3+
        s["stamina"]-s["falls"]*200-len(actions)*8+
        s["flow_chain"]*10
    )


def _unrecoverably_missed_medal(s):
    # This original route never permits running backward. A medal passed in
    # another lane without collection cannot be won by wishful route search.
    earned=set(s["medals_collected"])
    return any(m["x"]<s["x"] and m["x"] not in earned for m in s["medals"])


def plan_parkour_route(scene,settings=None,*,max_states=DEFAULT_MAX_STATES,
                       max_depth=96,beam_width=DEFAULT_BEAM_WIDTH):
    for name,value,minimum,maximum in (
        ("max_states",max_states,16,50000),
        ("max_depth",max_depth,1,MAX_TURNS),
        ("beam_width",beam_width,2,256),
    ):
        if type(value) is not int or not minimum<=value<=maximum:
            raise ParkourPlanningError("invalid bounded course search "+name)
    config=make_editor_document("parkour",settings)
    source=validate_advanced_scene(scene,config["settings"])
    if source["editor"]!="parkour":
        raise ParkourPlanningError("original parkour source required")
    rules=config["settings"]
    state=start(rules,source["seed"])
    apply_scene(state,rules,source["layout"])
    frontier=[(state,tuple())]
    visited={_signature(state)}
    evaluated=0
    breadth_pruned=False
    budget_reached=False
    best=(state,tuple())
    depth_reached=0

    def finished(actions):
        receipt=run_advanced_session("parkour",rules,list(actions),
                                     seed=source["seed"],scene=source)
        if not receipt["state"]["finished"] or receipt["state"]["failed"]:
            raise ParkourPlanningError("planner generated no physically completed original route")
        if not verify_advanced_session(receipt,rules):
            raise ParkourPlanningError("independent parkour evidence verification failed")
        report={
            "schema":SCHEMA,"status":"verified_solution",
            "source_digest":source["digest"],"settings_digest":config["digest"],
            "actions":list(actions),"action_count":len(actions),
            "gameplay_head_digest":receipt["head_digest"],
            "gameplay_receipt_digest":receipt["digest"],
            "earned_medals":receipt["state"]["medals_collected"],
            "actual_score":receipt["state"]["score"],
            "evaluated_successors":evaluated,
            "explored_signature_count":len(visited),
            "max_states":max_states,"max_depth":max_depth,
            "beam_width":beam_width,
            "independent_original_replay_verified":True,
            "exhaustive_search_proved":False,
            "native_hardware_verified":False,
            "publication_certified":False,
        }
        return {**report,"digest":_hash(report)}

    for depth in range(max_depth):
        depth_reached=depth
        successors=[]
        for physical,path in frontier:
            if physical["x"]==physical["exit_x"] and (
                len(physical["medals_collected"])==len(physical["medals"])
            ):
                return finished(path+("finish",))
            for action in PLANNER_ACTIONS:
                if evaluated>=max_states:
                    budget_reached=True
                    break
                candidate=deepcopy(physical)
                evaluated+=1
                try:
                    step(candidate,rules,action)
                except ParkourActionError:
                    continue
                if candidate["failed"] or _unrecoverably_missed_medal(candidate):
                    continue
                signature=_signature(candidate)
                if signature in visited:
                    continue
                visited.add(signature)
                next_path=path+(action,)
                successors.append((candidate,next_path))
                if _priority(candidate,next_path)>_priority(best[0],best[1]):
                    best=(candidate,next_path)
            if budget_reached:
                break
        if not successors:
            break
        successors.sort(key=lambda pair:(_priority(pair[0],pair[1]),
                                         -len(pair[1]),
                                         pair[1]),reverse=True)
        if len(successors)>beam_width:
            breadth_pruned=True
        frontier=successors[:beam_width]
        if budget_reached:
            break

    # Report the actual best observed physical attempt without counterfeit
    # victory or a logically unsound claim of unsolvability.
    report={
        "schema":SCHEMA,"status":"inconclusive_search_budget",
        "source_digest":source["digest"],"settings_digest":config["digest"],
        "actions":[],"action_count":0,
        "best_partial_actions":list(best[1]),
        "best_partial_x":best[0]["x"],
        "best_partial_medals":list(best[0]["medals_collected"]),
        "best_partial_health":best[0]["health"],
        "evaluated_successors":evaluated,
        "explored_signature_count":len(visited),
        "max_states":max_states,"max_depth":max_depth,
        "beam_width":beam_width,"search_depth_reached":depth_reached,
        "budget_reached":budget_reached,"beam_pruned":breadth_pruned,
        "independent_original_replay_verified":False,
        "exhaustive_search_proved":False,
        "native_hardware_verified":False,
        "publication_certified":False,
    }
    return {**report,"digest":_hash(report)}
