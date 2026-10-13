"""Bounded game-builder route rehearsal for authored original labyrinths.

Only the genuine maze transition engine can authorize traversal. Source keys,
phased walls, portals, floor transitions and actual damage are replayed; a
winning route is never inferred from static graph reachability. Inconclusive
results are not promoted to impossibility claims.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    MAX_TURNS,run_advanced_session,verify_advanced_session,
)
from .advanced_level_scenes import validate_advanced_scene
from .advanced_maze_runtime import MazeActionError,start,step,apply_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.maze_route_plan.v1"
BASE_ACTIONS=("north","south","east","west","ascend","descend",
              "warp","open","wait","rest","light_torch")
DIAGONALS=("northeast","northwest","southeast","southwest")
MAX_SEARCH=30000


class MazePlanningError(ValueError):
    """Invalid authored route proof, source identity or finite search budget."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _signature(s):
    # Include time because moving walls and exhausted resources are stateful.
    return (
        tuple(s["position"]),s["tick"],s["phase"],
        tuple(tuple(k) for k in s["collected_keys"]),s["door_open"],
        s["health"],s["stamina"],s["torches"],s["light"],
        s["collisions"],s["hazard_hits"],s["portal_uses"],
    )


def _priority(s,path):
    remaining=[k for k in s["keys"] if k not in s["collected_keys"]]
    goal=(remaining[0] if remaining else s["door"] if not s["door_open"]
          else s["exit"])
    point=s["position"]
    distance=sum(abs(a-b) for a,b in zip(point,goal))
    return (len(s["collected_keys"])*1600+(900 if s["door_open"] else 0)
            +point[2]*30-s["hazard_hits"]*80+s["health"]*3
            +s["stamina"]-distance*25-len(path)*3)


def plan_original_maze(scene,settings=None,*,max_states=12000,
                       max_depth=96,beam_width=96):
    for label,value,lo,hi in (
        ("max_states",max_states,8,MAX_SEARCH),
        ("max_depth",max_depth,1,MAX_TURNS),
        ("beam_width",beam_width,1,256),
    ):
        if type(value) is not int or not lo<=value<=hi:
            raise MazePlanningError("invalid original labyrinth search "+label)
    document=make_editor_document("maze",settings)
    rules=document["settings"]
    source=validate_advanced_scene(scene,rules)
    if source["editor"]!="maze":
        raise MazePlanningError("source-bound original labyrinth required")
    initial=start(rules,source["seed"])
    apply_scene(initial,rules,source["layout"])
    frontier=[(initial,())]
    seen={_signature(initial)}
    examined=0
    depth=0
    pruned=False
    exhausted=False
    best=(initial,())
    options=BASE_ACTIONS+(DIAGONALS if rules["topology"]=="braided" else ())

    def prove(commands):
        actual=run_advanced_session(
            "maze",rules,list(commands),seed=source["seed"],scene=source
        )
        if not actual["state"]["finished"] or actual["state"]["failed"]:
            raise MazePlanningError("proposed maze route failed real movement replay")
        if verify_advanced_session(actual,rules) is not True:
            raise MazePlanningError("independent maze run receipt failed verification")
        state=actual["state"]
        result={
            "schema":SCHEMA,"status":"replay_verified_exit",
            "source_digest":source["digest"],"settings_digest":document["digest"],
            "topology":state["topology"],"actions":list(commands),
            "action_count":len(commands),"final_health":state["health"],
            "actual_keys":len(state["collected_keys"]),
            "visited_floors":list(state["floor_visits"]),
            "actual_score":state["score"],
            "gameplay_receipt_digest":actual["digest"],
            "expanded_transitions":examined,"unique_physical_states":len(seen),
            "max_states":max_states,"max_depth":max_depth,"beam_width":beam_width,
            "independent_replay_verified":True,"exhaustive_search_proved":False,
            "native_hardware_certified":False,"publication_certified":False,
        }
        return {**result,"digest":_digest(result)}

    for turn in range(max_depth):
        depth=turn+1
        candidates=[]
        for physical,path in frontier:
            if (physical["position"]==physical["exit"] and physical["door_open"]
                and len(physical["collected_keys"])==len(physical["keys"])):
                return prove(path+("finish",))
            for action in options:
                if examined>=max_states:
                    exhausted=True;break
                future=deepcopy(physical)
                examined+=1
                try:
                    step(future,rules,action)
                except MazeActionError:
                    continue
                if future["failed"]:continue
                tag=_signature(future)
                if tag in seen:continue
                seen.add(tag)
                route=path+(action,)
                candidates.append((future,route))
                if _priority(future,route)>_priority(best[0],best[1]):
                    best=(future,route)
            if exhausted:break
        if not candidates:break
        candidates.sort(key=lambda pair:(
            _priority(pair[0],pair[1]),-len(pair[1]),pair[1],
        ),reverse=True)
        if len(candidates)>beam_width:pruned=True
        frontier=candidates[:beam_width]
        if exhausted:break
    for physical,path in frontier:
        if (physical["position"]==physical["exit"] and physical["door_open"]
            and len(physical["collected_keys"])==len(physical["keys"])):
            return prove(path+("finish",))
    result={
        "schema":SCHEMA,"status":"inconclusive_bounded_search",
        "source_digest":source["digest"],"settings_digest":document["digest"],
        "topology":rules["topology"],"actions":[],"action_count":0,
        "best_partial_actions":list(best[1]),
        "best_partial_position":list(best[0]["position"]),
        "best_partial_keys":len(best[0]["collected_keys"]),
        "best_partial_health":best[0]["health"],
        "expanded_transitions":examined,"unique_physical_states":len(seen),
        "max_states":max_states,"max_depth":max_depth,
        "beam_width":beam_width,"search_depth_reached":depth,
        "budget_reached":exhausted,"beam_pruned":pruned,
        "independent_replay_verified":False,"exhaustive_search_proved":False,
        "native_hardware_certified":False,"publication_certified":False,
    }
    return {**result,"digest":_digest(result)}


def verify_original_maze_plan(receipt,scene,settings=None):
    if type(receipt) is not dict or receipt.get("schema")!=SCHEMA:
        raise MazePlanningError("exact original maze route receipt required")
    rebuilt=plan_original_maze(
        scene,settings,max_states=receipt.get("max_states"),
        max_depth=receipt.get("max_depth"),beam_width=receipt.get("beam_width"),
    )
    if rebuilt!=receipt:
        raise MazePlanningError("route actions, source digest or search budget altered")
    return True


__all__=["SCHEMA","MazePlanningError","plan_original_maze",
         "verify_original_maze_plan"]
