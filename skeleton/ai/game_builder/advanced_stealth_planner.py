"""Bounded original infiltration planning for the supervised 10x8 stealth editor.

The planner proves spatial feasibility of authored missions under explicitly
threat-free rehearsal rules. It does NOT certify live guard/camera evasion,
native engine execution, store distribution, or mission quality.
"""
from __future__ import annotations

from hashlib import sha256
from heapq import heappush, heappop
import json

from .advanced_stealth_runtime import (
    DIRECTIONS, WIDTH, HEIGHT, StealthActionError, _distance,
    normalize_layout,
)
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .system_editors import make_editor_document


SCHEMA="skeleton.game_builder.stealth_route_plan.v1"


class StealthPlanningError(ValueError):
    """Bounded planning input, state limit, or determinism contract violated."""


def _digest(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _target_distance(pos,targets):
    return min((_distance(pos,p) for p in targets),default=0)


def _heuristic(state,config,layout):
    x,y,keys,doors,hacked,archive,intel,cameras,hacks=state
    p=[x,y]
    mission=config["mission"]
    if mission=="archive":
        if not archive:
            if hacked or keys:
                return max(0,_distance(p,layout["objective"])-1)+2
            goals=list(layout["keycards"])
            if hacks>0:goals.append(layout["terminal"])
            return max(0,_target_distance(p,goals)-1)+4
    elif mission=="sabotage":
        if not hacked:
            return max(0,_distance(p,layout["terminal"])-1)+3
        if not cameras:
            return max(0,_target_distance(p,layout["cameras"])-1)+2
    else:
        acquired=intel.bit_count()
        if acquired<config["intel_target"]:
            remaining=[p for i,p in enumerate(layout["intel"])
                       if not intel&(1<<i)]
            return max(0,_target_distance(p,remaining)-1)+config["intel_target"]-acquired
    return max(0,_distance(p,layout["extraction"])-1)+1


def _goal(state,config,layout):
    x,y,keys,doors,hacked,archive,intel,cameras,hacks=state
    mission=config["mission"]
    reached=(archive if mission=="archive" else
             hacked and cameras!=0 if mission=="sabotage" else
             intel.bit_count()>=config["intel_target"])
    return bool(reached and _distance([x,y],layout["extraction"])<=1)


def _neighbors(state,config,layout):
    x,y,keys,doors,hacked,archive,intel,cameras,hacks=state
    player=[x,y]
    walls={tuple(p) for p in layout["walls"]}
    locked={tuple(p):i for i,p in enumerate(layout["doors"])}
    vents={tuple(p) for p in layout["vents"]}
    for direction,(dx,dy) in DIRECTIONS.items():
        xx,yy=x+dx,y+dy
        if not (0<=xx<WIDTH and 0<=yy<HEIGHT):
            continue
        tile=(xx,yy)
        if tile in walls or (tile in locked and not doors&(1<<locked[tile])):
            continue
        move=("crouch_" if tile in vents else "move_")+direction
        yield move,(xx,yy,keys,doors,hacked,archive,intel,cameras,hacks)
    for i,key in enumerate(layout["keycards"]):
        if not keys&(1<<i) and _distance(player,key)<=1:
            # The real engine takes the first reachable finite keycard.
            if any(not keys&(1<<j) and _distance(player,q)<=1
                   for j,q in enumerate(layout["keycards"][:i])):
                continue
            yield "collect_keycard",(x,y,keys|(1<<i),doors,hacked,archive,intel,cameras,hacks)
            break
    for i,door in enumerate(layout["doors"]):
        if not doors&(1<<i) and _distance(player,door)<=1:
            if keys or hacks:
                yield "hack_door",(
                    x,y,keys,doors|(1<<i),hacked,archive,intel,cameras,
                    hacks if keys else hacks-1)
            break
    if not hacked and hacks>0 and _distance(player,layout["terminal"])<=1:
        yield "hack_terminal",(x,y,keys,doors,1,archive,intel,cameras,hacks-1)
    if (not archive and _distance(player,layout["objective"])<=1
        and (hacked or keys)):
        yield "steal",(x,y,keys,doors,hacked,1,intel,cameras,hacks)
    for i,item in enumerate(layout["intel"]):
        if not intel&(1<<i) and _distance(player,item)<=1:
            if any(not intel&(1<<j) and _distance(player,q)<=1
                   for j,q in enumerate(layout["intel"][:i])):
                continue
            yield "collect_intel",(x,y,keys,doors,hacked,archive,
                                   intel|(1<<i),cameras,hacks)
            break
    for i,camera in enumerate(layout["cameras"]):
        if not cameras&(1<<i) and _distance(player,camera)<=1:
            if any(not cameras&(1<<j) and _distance(player,q)<=1
                   for j,q in enumerate(layout["cameras"][:i])):
                continue
            yield "disable_camera",(x,y,keys,doors,hacked,archive,
                                    intel,cameras|(1<<i),hacks)
            break


def plan_stealth_route(scene,settings=None,*,max_states=30000,max_depth=96):
    """Return source-bound shortest-first geometric mission plan and replay.

    The AI must treat a successful route as a SPATIAL REHEARSAL ONLY. Guards
    patrol independently and can detect/capture this same route at runtime.
    The original reviewed scene and original user settings are NEVER changed.
    """
    if type(max_states) is not int or not 200<=max_states<=150000:
        raise StealthPlanningError("state planning budget must be in 200..150000")
    if type(max_depth) is not int or not 1<=max_depth<=128:
        raise StealthPlanningError("max-depth must be within game replay cap")
    config=make_editor_document("stealth",settings)
    authored=validate_advanced_scene(scene,config["settings"])
    if authored["editor"]!="stealth":
        raise StealthPlanningError("original stealth editor scene is mandatory")
    rules=config["settings"]
    layout=normalize_layout(rules,authored["layout"])
    x,y=layout["spawn"]
    origin=(x,y,0,0,0,0,0,0,rules["hacking_charges"])
    # Heap order uses deterministic priority, then g/counter to avoid
    # platform-specific ordering of mixed Python object identities.
    heap=[];serial=0
    heappush(heap,(_heuristic(origin,rules,layout),0,serial,origin))
    best={origin:0};parents={}
    explored=0;found=None
    while heap and explored<max_states:
        estimate,depth,serial,state=heappop(heap)
        if best.get(state)!=depth:
            continue
        explored+=1
        if _goal(state,rules,layout):
            found=state
            break
        if depth>=max_depth-1:
            continue
        for action,new in _neighbors(state,rules,layout):
            step_cost=depth+1
            if best.get(new,1000000)<=step_cost:
                continue
            best[new]=step_cost
            parents[new]=(state,action)
            serial+=1
            heappush(heap,(step_cost+_heuristic(new,rules,layout),
                           step_cost,serial,new))
    commands=[]
    if found is not None:
        cursor=found
        while cursor!=origin:
            parent,command=parents[cursor]
            commands.append(command)
            cursor=parent
        commands.reverse()
        commands.append("extract")
    # Distinguish solver exhaustion from static unsatisfiability.
    feasibility=("rehearsal_route_found" if found is not None else
                 "unproven_budget_exhausted" if heap else
                 "no_route_under_registered_spatial_actions")
    rehearsal_digest=None;verified=False
    if commands:
        rehearsal_settings=dict(rules)
        rehearsal_settings.update({
            "guard_count":0,"camera_range":0,"contact_damage":0,
            "alarm_damage":0,"fail_on_alarm":False,
        })
        rehearsal_scene=make_advanced_scene(
            "stealth",rehearsal_settings,seed=authored["seed"],
            scene_id=authored["scene_id"],layout=layout)
        simulated=run_advanced_session(
            "stealth",rehearsal_settings,commands,
            seed=authored["seed"],scene=rehearsal_scene)
        if not simulated["state"]["finished"] or not simulated["state"]["extracted"]:
            raise StealthPlanningError("original reference rehearsal did not extract")
        verified=verify_advanced_session(simulated,rehearsal_settings)
        rehearsal_digest=simulated["digest"]
    data={
        "schema":SCHEMA,
        "editor":"stealth","mission":rules["mission"],
        "scene_digest":authored["digest"],
        "settings_digest":config["digest"],
        "feasibility":feasibility,
        "route":commands,
        "route_turn_count":len(commands),
        "states_explored":explored,
        "state_limit":max_states,"depth_limit":max_depth,
        "rehearsal_verified":verified,
        "rehearsal_session_digest":rehearsal_digest,
        "actual_security_evasion_verified":False,
        "native_engine_verified":False,
        "source_mutated":False,
        "authority":"threat_free_spatial_rehearsal_only",
    }
    return {**data,"digest":_digest(data)}


__all__=["SCHEMA","StealthPlanningError","plan_stealth_route"]
