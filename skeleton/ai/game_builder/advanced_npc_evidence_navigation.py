"""Audited physical navigation for real first-hand NPC investigations.

Given a complete, independently reconstructed episodic original world, plan
and actually simulate finite player moves, rest and testimony/repair actions.
Canonical 7x7 obstacles, stamina, NPC mobility, trust, nightfall, rumor and
quest expiry are authoritative. This is a proofed *preview*; the studio must
append its real original actions to a campaign before they change that world.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from hashlib import sha256
import json

from .advanced_physics_episodic_world import (
    run_episodic_physics_world,verify_episodic_physics_world,
)
from .advanced_quest_director_runtime import (
    SIDE,CELLS,step as world_step,QuestDirectorError,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.npc_evidence_navigation.v1"
OBJECTIVES=("testimony","repair","aid","resolve")
MAX_MOVES=24

class EvidenceNavigationError(ValueError):
    """Requested investigation or action cannot be sourced to the world."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _distance(a,b):
    return abs(a%SIDE-b%SIDE)+abs(a//SIDE-b//SIDE)


def _route(state,goal):
    """Shortest authored path to a real tile adjacent to the target."""
    start=state["player"]
    if _distance(start,goal)<=1:
        return ()
    blockers=set(state["world"]["obstacles"])
    queue=deque([(start,())])
    visited={start}
    # Stable tie-break: north, west, east, south. Never teleport diagonally.
    steps=(("north",0,-1),("west",-1,0),
           ("east",1,0),("south",0,1))
    while queue:
        cell,route=queue.popleft()
        x,y=cell%SIDE,cell//SIDE
        for verb,dx,dy in steps:
            nx,ny=x+dx,y+dy
            if not 0<=nx<SIDE or not 0<=ny<SIDE:
                continue
            next_cell=ny*SIDE+nx
            if next_cell in visited or next_cell in blockers:
                continue
            new=route+(verb,)
            if _distance(next_cell,goal)<=1:
                return new
            queue.append((next_cell,new))
            visited.add(next_cell)
    return None


def _quest(world,quest_id):
    return next((q for q in world["quests"] if q["id"]==quest_id),None)


def _eligible_npc(world,quest,cfg):
    eligible=[]
    for npc in world["npcs"]:
        if (npc["id"] not in quest["witnesses"] or
            npc["id"] in quest["testimonies"] or
            not any(m["event_id"]==quest["origin_event"] for m in npc["memories"]) or
            npc["trust"]<cfg["testimony_trust_floor"] or
            npc["suspicion"]>npc["trust"]+cfg["testimony_suspicion_tolerance"]):
            continue
        path=_route(world,npc["cell"])
        if path is not None:
            eligible.append((len(path),npc["id"]))
    return min(eligible)[1] if eligible else None


def navigate_verified_investigation(campaign,episodes,scene,
                                    quest_settings=None,*,quest_id=0,
                                    objective="testimony"):
    if type(quest_id) is not int or not 0<=quest_id<=11 or objective not in OBJECTIVES:
        raise EvidenceNavigationError("bounded original quest and objective are required")
    try:
        verify_episodic_physics_world(campaign,episodes,scene,quest_settings)
        cfg=make_editor_document("quest_director",quest_settings)["settings"]
        state=deepcopy(campaign["world_state"])
        quest=_quest(state,quest_id)
        if quest is None or quest["origin_actor"]!="external:physics":
            raise EvidenceNavigationError("physical-source authored NPC quest does not exist")
        trace=[]
        actions=[]
        previous=_digest({"source":campaign["digest"],
                          "quest":quest_id,"objective":objective})
        npc_id=_eligible_npc(state,quest,cfg) if objective=="testimony" else None
        outcome=None
        target_site=next(s for s in state["sites"] if s["id"]==quest["site_id"])
        if quest["status"]!="active":
            outcome="quest_not_active"
        elif objective=="testimony" and npc_id is None:
            outcome=("already_corroborated" if
                     len(quest["testimonies"])>=cfg["evidence_min"]
                     else "no_credible_firsthand_witness")
        elif objective=="repair" and target_site["integrity"]>=cfg["site_integrity"]:
            outcome="site_already_restored"
        elif objective=="aid" and (state["supplies"]<cfg["help_supplies"] or
              (cfg["help_supplies"]==0 and
               target_site["integrity"]>=cfg["site_integrity"])):
            outcome="real_material_relief_requires_finite_source_resources"
        elif objective=="resolve" and (quest["choice"] is None or
            len(quest["testimonies"])<cfg["evidence_min"] or
            quest["material_actions"]<cfg["consequence_depth"]):
            outcome="real_material_or_testimony_prerequisites_missing"

        def enact(command):
            nonlocal previous
            events=world_step(state,cfg,command)
            item={
                "action":command,
                "turn":state["turn"],"tick":state["tick"],
                "player":state["player"],"stamina":state["stamina"],
                "events":list(events),
                "npc_positions":[n["cell"] for n in state["npcs"]],
                "site_integrity":[s["integrity"] for s in state["sites"]],
                "testimonies":list(_quest(state,quest_id)["testimonies"]),
            }
            head=_digest({"previous":previous,"step":item})
            trace.append({**item,"previous_hash":previous,"head_hash":head})
            previous=head
            actions.append(command)

        while outcome is None and len(actions)<MAX_MOVES:
            quest=_quest(state,quest_id)
            if state["finished"] or state["failed"] or quest["status"]!="active":
                outcome="original_quest_expired_or_world_terminal"
                break
            if objective=="testimony":
                npc=next(n for n in state["npcs"] if n["id"]==npc_id)
                if (not any(m["event_id"]==quest["origin_event"] for m in npc["memories"])
                    or npc["trust"]<cfg["testimony_trust_floor"] or
                    npc["suspicion"]>npc["trust"]+cfg["testimony_suspicion_tolerance"]):
                    outcome="witness_memory_or_credibility_lost"
                    break
                target=npc["cell"]
                final="speak:"+str(npc_id)
                cost=0
            else:
                target=target_site["cell"]
                final=("repair:"+str(quest["site_id"]) if objective=="repair"
                       else "help:"+str(quest["site_id"]) if objective=="aid"
                       else "resolve:"+str(quest_id))
                cost=cfg["action_stamina"] if objective in ("repair","aid") else 0
                if objective=="repair" and state["supplies"]<cfg["repair_supplies"]:
                    outcome="real_material_supplies_required"
                    break
                if objective=="repair" and target_site["integrity"]>=cfg["site_integrity"]:
                    outcome="site_already_restored"
                    break
                if objective=="aid" and (state["supplies"]<cfg["help_supplies"] or
                    (cfg["help_supplies"]==0 and
                     target_site["integrity"]>=cfg["site_integrity"])):
                    outcome="real_material_relief_requires_finite_source_resources"
                    break
            path=_route(state,target)
            if path is None:
                outcome="authored_world_path_blocked"
                break
            if path:
                command=path[0]
                required=cfg["movement_stamina"]
            else:
                command=final
                required=cost
            if state["stamina"]<required:
                if cfg["rest_stamina"]<=0:
                    outcome="real_stamina_cannot_recover"
                    break
                command="rest"
            enact(command)
            if command==final:
                updated=_quest(state,quest_id)
                if objective=="testimony":
                    outcome=("firsthand_testimony_recorded" if
                         npc_id in updated["testimonies"] else
                         "no_firsthand_testimony_was_earned")
                elif objective=="repair":
                    outcome="real_site_repair_enacted"
                elif objective=="aid":
                    outcome="finite_original_community_aid_delivered"
                else:
                    outcome=("original_quest_resolved" if
                             updated["status"]=="resolved" else
                             "quest_resolution_not_earned")
                break
        if outcome is None:
            outcome="finite_route_budget_exhausted"
        record={
            "schema":SCHEMA,"campaign_digest":campaign["digest"],
            "quest_id":quest_id,"objective":objective,
            "original_quest_event":quest["origin_event"],
            "target_npc_id":npc_id,"world_scene_digest":scene["digest"],
            "planned_and_simulated_actions":actions,
            "route_steps":trace,"next_quest_state":_quest(state,quest_id),
            "end_world_state":state,
            "outcome":outcome,"head_hash":previous,
            "original_campaign_mutated":False,
            "automatic_rewards_or_publication":False,
        }
    except EvidenceNavigationError:
        raise
    except (ValueError,KeyError,TypeError,IndexError,StopIteration) as exc:
        raise EvidenceNavigationError(
            "independent original world, witness path or finite action failed"
        ) from exc
    return {**record,"digest":_digest(record)}


def verify_investigation_navigation(proof,campaign,episodes,scene,
                                   quest_settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise EvidenceNavigationError("signed original eyewitness route required")
    try:
        rerun=navigate_verified_investigation(
            campaign,episodes,scene,quest_settings,
            quest_id=proof["quest_id"],objective=proof["objective"])
    except (KeyError,TypeError) as exc:
        raise EvidenceNavigationError("route proof missing signed original target") from exc
    if rerun!=proof:
        raise EvidenceNavigationError("altered witness, path, testimony or quest action")
    return True


__all__=["SCHEMA","OBJECTIVES","MAX_MOVES","EvidenceNavigationError",
         "navigate_verified_investigation","verify_investigation_navigation"]
