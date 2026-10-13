"""Causally witnessed original sandbox quests with finite civic funding.

Witnesses are real region-local NPCs, with bounded proximity and a separate
acoustic hearing radius. Every story trigger is derived from a successful game
transition, an observed coordinate and a signed deterministic evidence payload.
The story machine NEVER executes text instructions or fabricates inventory.
"""
from __future__ import annotations
from hashlib import sha256
import json


TRIGGERS={
    "chop":"forest_restoration",
    "hunt":"wildlife_stewardship",
    "ignite":"fire_safety",
    "demolish":"civic_reconstruction",
}
HEARD=frozenset(("ignite","demolish","hunt"))
REWARDS={
    "forest_restoration":"tree_planting_reward",
    "wildlife_stewardship":"animal_conservation_reward",
    "fire_safety":"fire_control_reward",
    "civic_reconstruction":"local_rebuilding_reward",
    "community_relief":"emergency_supplies_reward",
}


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,
                             separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _distance(a,b):
    return abs(a%8-b%8)+abs(a//8-b//8)


def _qualified_witnesses(state,config,site,action):
    sight=config["witness_radius"]-(1 if state["weather"]=="storm" else 0)
    results=[]
    for npc in state["settlers"]:
        if npc["region"]!=state["region"] or npc["health"]<=0:
            continue
        dist=_distance(npc["cell"],site)
        if dist<=max(0,sight):
            results.append({"id":npc["id"],"perception":"saw","distance":dist})
        elif action in HEARD and dist<=config["sound_radius"]:
            results.append({"id":npc["id"],"perception":"heard","distance":dist})
    return sorted(results,key=lambda w:w["id"])


def _record(state,config,cause,site,witnesses,events,source):
    if not witnesses:
        return
    evidence={
        "schema":"skeleton.game_builder.original_witness.v1",
        "sequence":state["witness_sequence"],"turn":state["turn"],
        "previous_witness_digest":state["witness_head"],
        "day":state["day"],"region":state["region"],
        "site":site,"cause":cause,
        "witnesses":witnesses,"source":source,
    }
    evidence["digest"]=_digest(evidence)
    state["witness_head"]=evidence["digest"]
    state["witness_sequence"]+=1
    state["observations"].append(evidence)
    limit=config["observation_limit"]
    if len(state["observations"])>limit:
        state["observations"]=state["observations"][-limit:]
    events.append("actual_npc_witnessed_original_"+cause)
    kind=TRIGGERS.get(cause)
    if cause=="shortage":
        kind="community_relief"
    if kind is None or len(state["quests"])>=config["quest_limit"]:
        return
    # One quest per *real* region/asset/problem. Completed quests do not
    # regenerate credit rewards from the same witnessed historical event.
    unique="r"+str(state["region"])+"_s"+str(site)+"_"+kind
    if any(q["id"]==unique for q in state["quests"]):
        return
    quest={
       "id":unique,"type":kind,"site":site,"region":state["region"],
       "witness_id":witnesses[0]["id"],
       "observation_digest":evidence["digest"],"opened_turn":state["turn"],
       "status":"open","completed_turn":None,"paid_from_fund":0,
    }
    state["quests"].append(quest)
    events.append("real_observation_opened_original_"+kind+"_quest")


def observe_game_action(state,config,action,site,events):
    cause=action.split(":")[0]
    if cause not in TRIGGERS:
        return
    if site is None:
        raise ValueError("witnessed original physical action requires real map coordinates")
    witnesses=_qualified_witnesses(state,config,site,cause)
    _record(state,config,cause,site,witnesses,events,
            "successful_spatial_original_action")


def observe_community_shortage(state,config,events):
    if not any("actual_settler_food_water_shortage"==e for e in events):
        return
    active=[s for s in state["settlers"] if s["region"]==state["region"]
            and s["health"]>0]
    if not active:
        return
    agent=active[0]
    witnesses=[{"id":agent["id"],"perception":"self_report",
                "distance":0}]
    _record(state,config,"shortage",agent["cell"],witnesses,
            events,"real_community_food_water_ledger")


def settle_observed_quests(state,config,action,site,events):
    # The action has already passed authoritative gameplay validation and
    # actually changed the physical world. This is NOT a free quest command.
    region=state["region"]
    cells=state["regions"][str(region)]
    for q in state["quests"]:
        if q["status"]!="open" or q["region"]!=region:
            continue
        target=cells[q["site"]]
        kind=q["type"]
        solved=(
          (kind=="forest_restoration" and action.startswith("plant_tree:")
           and site==q["site"] and target["sapling"]>0)
          or (kind=="wildlife_stewardship" and action.startswith("tame:")
              and site is not None and cells[site]["tamed"])
          or (kind=="fire_safety" and action.startswith("extinguish:")
              and site==q["site"] and target["fire"]==0)
          or (kind=="civic_reconstruction" and action.startswith("build:")
              and site==q["site"] and target["building"] is not None)
          or (kind=="community_relief" and action.startswith("donate:")
              and state["community_food"]>=config["relief_food"]
              and state["community_water"]>=config["relief_water"])
        )
        if not solved:
            continue
        paid=min(config["quest_reward"],state["civic_grant_reserve"])
        state["civic_grant_reserve"]-=paid
        state["credits"]+=paid
        q["status"]="completed"
        q["completed_turn"]=state["turn"]
        q["paid_from_fund"]=paid
        events.append("original_witnessed_"+kind+"_quest_really_completed")


__all__=["TRIGGERS","REWARDS","observe_game_action",
         "observe_community_shortage","settle_observed_quests"]
