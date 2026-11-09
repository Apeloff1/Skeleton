"""Original bounded world-progression solver with independently replayed evidence.

Models persistent visited rooms and acquired powers, searches a real authored
portal graph, and emits legal enemy-fight, relic-claim and traversal commands.
Rehearses in a deliberate threat-free diagnostic mode, not as a promise of
live-game combat survivability, publication readiness or native parity.
"""
from __future__ import annotations
from hashlib import sha256
from heapq import heappop,heappush
import json

from .advanced_metroidvania_runtime import (
    POWERS,ExplorationActionError,normalize_layout,
)
from .advanced_gameplay_runtime import run_advanced_session,verify_advanced_session
from .advanced_level_scenes import validate_advanced_scene,make_advanced_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.original_world_route_plan.v1"
MAX_STATES=50000
MAX_ACTIONS=128


class ExplorationPlanningError(ValueError):
    """Impossible bounded exploration search, untrusted source or bad parameters."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _combat_actions(room,config):
    strikes=(room["foe"]+config["attack_power"]-1)//config["attack_power"]
    if room["id"]==0:
        return strikes
    return strikes


def _neighbors(state,layout,settings):
    current,visited,powers=state
    rooms=layout["rooms"]
    for edge in layout["passages"]:
        target=(edge["b"] if edge["a"]==current else
                edge["a"] if edge["b"]==current else None)
        if target is None:continue
        gate=edge["gate"]
        if gate is not None and not (powers & (1<<POWERS.index(gate))):
            continue
        room=rooms[target]
        fresh=not (visited & (1<<target))
        battle=(_combat_actions(room,settings) if fresh else 0)
        commands=["travel:"+str(target)]+["attack"]*battle
        newpowers=powers
        if fresh and room["ability"] is not None:
            newpowers|=1<<POWERS.index(room["ability"])
            commands.append("claim")
        yield ((target,visited|(1<<target),newpowers),commands)


def plan_original_world(scene,settings=None,*,max_states=MAX_STATES,
                        max_actions=MAX_ACTIONS):
    if type(max_states) is not int or not 200<=max_states<=100000:
        raise ExplorationPlanningError("world-search node budget must be in 200..100000")
    if type(max_actions) is not int or not 1<=max_actions<=128:
        raise ExplorationPlanningError("world rehearsal length exceeds replay cap")
    config=make_editor_document("metroidvania",settings)
    source=validate_advanced_scene(scene,config["settings"])
    if source["editor"]!="metroidvania":
        raise ExplorationPlanningError("authored original interconnected-world scene required")
    rules=config["settings"]
    layout=normalize_layout(rules,source["layout"])
    start=(layout["entry"],1<<layout["entry"],0)
    # Minimum number of game actions, with stable expansion and no
    # assumption that all player-authored gates are breakable.
    heap=[(0,0,start)]
    best={start:0};parents={};seen=0;count=0
    goal=None
    while heap and seen<max_states:
        length,_,state=heappop(heap)
        if best.get(state)!=length:
            continue
        seen+=1
        room,visited,powers=state
        if room==layout["guardian"]:
            boss_actions=(layout["guardian_health"]+rules["attack_power"]-1)//rules["attack_power"]
            if length+boss_actions<=max_actions:
                goal=state
                break
        for next_state,commands in _neighbors(state,layout,rules):
            next_cost=length+len(commands)
            if next_cost>max_actions:
                continue
            if next_cost>=best.get(next_state,10**9):
                continue
            count+=1;best[next_state]=next_cost
            parents[next_state]=(state,commands)
            heappush(heap,(next_cost,count,next_state))
    actions=[]
    if goal is not None:
        cursor=goal
        while cursor!=start:
            previous,commands=parents[cursor]
            actions[0:0]=commands
            cursor=previous
        actions.extend(["attack"]*((layout["guardian_health"]+
                       rules["attack_power"]-1)//rules["attack_power"]))
    if goal is not None and len(actions)>max_actions:
        raise ExplorationPlanningError("planner bypassed hard transcript size cap")
    result_status=("verified_diagnostic_route" if goal is not None
                   else "unproven_budget_exhausted" if seen>=max_states
                   else "no_route_within_authored_action_cap")
    proof=None;verified=False
    if goal is not None:
        # Source stays untouched. New rehearsal settings deliberately remove
        # direct damage while preserving the real topology, enemy HP,
        # collectible ability gates, credits and boss hit-point budget.
        rehearsal_settings=dict(rules)
        rehearsal_settings.update({
            "foe_damage":0,"hazard_damage":0,"armor":max(1,rules["armor"]),
            "boss_damage":1,"ending_policy":"campaign",
        })
        rehearsal=make_advanced_scene(
            "metroidvania",rehearsal_settings,seed=source["seed"],
            scene_id=source["scene_id"],layout=layout)
        session=run_advanced_session(
            "metroidvania",rehearsal_settings,actions,
            seed=source["seed"],scene=rehearsal)
        if not session["state"]["boss_defeated"] or not session["state"]["finished"]:
            raise ExplorationPlanningError("independently executed progression did not defeat guardian")
        verified=verify_advanced_session(session,rehearsal_settings)
        proof=session["digest"]
    payload={
        "schema":SCHEMA,
        "editor":"metroidvania",
        "original_source_digest":source["digest"],
        "original_configuration_digest":config["digest"],
        "regions":len(layout["rooms"]),"powers":len(POWERS),
        "route":actions,"route_turn_count":len(actions),
        "feasibility":result_status,
        "search_nodes_explored":seen,"search_nodes_limit":max_states,
        "action_budget":max_actions,
        "rehearsal_verified":verified,"rehearsal_digest":proof,
        "original_play_survivability_verified":False,
        "native_execution_verified":False,
        "source_mutated":False,
        "authority":"damage_free_ability_route_rehearsal_only",
    }
    return {**payload,"digest":_digest(payload)}


__all__=["SCHEMA","MAX_STATES","ExplorationPlanningError","plan_original_world"]
