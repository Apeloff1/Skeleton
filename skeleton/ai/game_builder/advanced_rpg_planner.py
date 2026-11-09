"""Deterministic AI RPG director: plan original witnessed story, prove by play.

Source-bound graph routing uses real movement and combat, not direct mutation
of quest flags. Planning is a bounded candidate; ONLY independent complete
gameplay replay can certify a chapter, while inaccessible worlds stay
inconclusive rather than being declared logically unwinnable.
"""
from __future__ import annotations

from copy import deepcopy
from collections import deque
from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    AdvancedRuntimeError,run_advanced_session,verify_advanced_session,
)
from .advanced_level_scenes import validate_advanced_scene
from .advanced_rpg_runtime import (
    MOVES,RPGActionError,start,apply_scene,step,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.original_rpg_story_plan.v1"
MAX_SEARCH_NODES=8000


class RPGPlanningError(ValueError):
    """Invalid planner/source custody or forged story evidence."""


class _Inconclusive(Exception):
    pass


def _digest(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _route(config,state,destination,*,near=False,max_nodes=8000):
    start_pos=tuple(state["position"])
    target=tuple(destination)
    blockers={tuple(p) for p in state["blocked"]}
    def reached(p):
        return (abs(p[0]-target[0])+abs(p[1]-target[1])<=1
                if near else p==target)
    if reached(start_pos):return ()
    queue=deque([(start_pos,())])
    visited={start_pos}
    checked=0
    while queue and checked<max_nodes:
        point,path=queue.popleft()
        checked+=1
        for action in ("north","east","south","west"):
            dx,dy=MOVES[action]
            next_point=(point[0]+dx,point[1]+dy)
            if (next_point in visited or next_point in blockers or
                not 0<=next_point[0]<config["world_width"] or
                not 0<=next_point[1]<config["world_height"]):
                continue
            next_path=path+(action,)
            if reached(next_point):return next_path
            visited.add(next_point)
            queue.append((next_point,next_path))
    raise _Inconclusive("no physical route found within bounded search")


def plan_original_rpg_chapter(scene,settings=None,*,max_nodes=MAX_SEARCH_NODES,
                              max_actions=128,social_choice="choose:trust"):
    for key,value,lo,hi in (
        ("max_nodes",max_nodes,1,MAX_SEARCH_NODES),
        ("max_actions",max_actions,1,128),
    ):
        if type(value) is not int or not lo<=value<=hi:
            raise RPGPlanningError("invalid finite original RPG search "+key)
    if social_choice not in ("choose:trust","choose:trade","choose:challenge"):
        raise RPGPlanningError("unregistered social decision")
    doc=make_editor_document("rpg",settings)
    rules=doc["settings"]
    src=validate_advanced_scene(scene,rules)
    if src["editor"]!="rpg":
        raise RPGPlanningError("only actual source-bound RPG stories can be planned")
    model=start(rules,src["seed"])
    apply_scene(model,rules,src["layout"])
    actions=[]
    checks=0

    def act(command):
        if len(actions)>=max_actions:raise _Inconclusive("player action budget")
        try:
            step(model,rules,command)
        except RPGActionError as exc:
            raise _Inconclusive("real RPG prerequisite: "+str(exc)) from exc
        actions.append(command)

    def travel(point,near=False):
        nonlocal checks
        route=_route(rules,model,point,near=near,max_nodes=max_nodes)
        checks+=len(route)
        for command in route:
            act(command)

    try:
        travel(model["npcs"][0]["at"],near=True)
        act("accept")
        travel(model["relic"])
        act("investigate")
        act("gather")
        travel(model["enemy"],near=True)
        while model["enemy_hp"]>0:
            # Select the actor with the strongest affordable living attack;
            # attacks are paid and resolved through the live encounter model.
            actor=model["party"][model["selected"]]
            if actor["hp"]<=rules["enemy_damage"]:
                candidates=[p for p in model["party"] if p["hp"]>rules["enemy_damage"]]
                if not candidates:raise _Inconclusive("party cannot survive source encounter")
                act("select:"+str(candidates[0]["id"]))
            act("attack")
        travel(model["npcs"][1]["at"],near=True)
        act(social_choice)
        travel(model["npcs"][0]["at"],near=True)
        act("turn_in")
        if not all(v=="completed" for v in model["quests"].values()):
            raise _Inconclusive("quest contract did not physically complete")
        travel(model["exit"])
        act("finish")
        if not model["chapter_claimed"]:
            raise _Inconclusive("authored chapter did not complete")
        receipt=run_advanced_session(
            "rpg",rules,actions,seed=src["seed"],scene=src
        )
        if not receipt["state"]["chapter_claimed"] or (
            receipt["state"]["chapters_completed"]!=1
        ) or not verify_advanced_session(receipt,rules):
            raise RPGPlanningError("RPG director proposed an unverified story")
        body={
            "schema":SCHEMA,"status":"replay_verified_chapter",
            "source_digest":src["digest"],"settings_digest":doc["digest"],
            "social_choice":social_choice,"actions":list(actions),
            "action_count":len(actions),
            "earned_quests":list(receipt["state"]["quests"].keys()),
            "npc_memories":len(receipt["state"]["social_memories"]),
            "resulting_faction_reputation":dict(receipt["state"]["factions"]),
            "postgame_available":rules["persistent_world"],
            "replay_digest":receipt["digest"],
            "max_nodes":max_nodes,"max_actions":max_actions,
            "searched_route_steps":checks,
            "independent_replay_verified":True,
            "exhaustive_search_proved":False,"native_hardware_verified":False,
            "publication_certified":False,
        }
        return {**body,"digest":_digest(body)}
    except _Inconclusive as exc:
        body={
            "schema":SCHEMA,"status":"inconclusive_bounded_story",
            "source_digest":src["digest"],"settings_digest":doc["digest"],
            "social_choice":social_choice,"actions":[],
            "action_count":0,"best_partial_actions":list(actions),
            "best_partial_quests":dict(model["quests"]),
            "best_partial_position":list(model["position"]),
            "limitation":str(exc),
            "max_nodes":max_nodes,"max_actions":max_actions,
            "searched_route_steps":checks,
            "independent_replay_verified":False,
            "exhaustive_search_proved":False,"native_hardware_verified":False,
            "publication_certified":False,
        }
        return {**body,"digest":_digest(body)}


def verify_original_rpg_plan(receipt,scene,settings=None):
    if type(receipt) is not dict or receipt.get("schema")!=SCHEMA:
        raise RPGPlanningError("exact signed original RPG director plan required")
    result=plan_original_rpg_chapter(
        scene,settings,max_nodes=receipt.get("max_nodes"),
        max_actions=receipt.get("max_actions"),
        social_choice=receipt.get("social_choice"),
    )
    if result!=receipt:
        raise RPGPlanningError("original RPG source, actions or witness proof changed")
    return True


__all__=["SCHEMA","RPGPlanningError","plan_original_rpg_chapter",
         "verify_original_rpg_plan"]
