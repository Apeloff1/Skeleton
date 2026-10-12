"""Typed if/all/any/not rules for original source-verified living game worlds.

Condition evaluation reads only independently replayed NPC facts. Matching
rules can propose or (with explicit local operator permission) append *actual*
canonical path/interview/aid/repair/resolve commands to the last episode.
No rule may author original game rewards, memory, testimony, gold or HP.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_physics_episodic_world import (
    run_episodic_physics_world,verify_episodic_physics_world,
    MAX_EPISODES,MAX_ACTIONS_PER_EPISODE,MAX_TOTAL_WORLD_ACTIONS,
)
from .advanced_npc_evidence_navigation import (
    navigate_verified_investigation,verify_investigation_navigation,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.npc_conditional_rules.v1"
MAX_RULES=12
MAX_NODES=16
MAX_DEPTH=4
MAX_APPLIED=4
GOALS=("testimony","repair","aid","resolve")
FACTS={
    "source_eyewitnesses",
    "real_testimonies",
    "reported_rumors",
    "real_material_actions",
    "site_integrity",
    "player_supplies",
    "player_stamina",
    "world_tick",
    "quest_active",
    "quest_support_chosen",
    "quest_exploit_chosen",
    "external_physical_origin",
}

class NPCConditionalError(ValueError):
    """Conditional NPC rule, source replay or earned action was rejected."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _predicate(node,counts,depth=0):
    if type(node) is not dict or depth>MAX_DEPTH:
        raise NPCConditionalError("bounded typed original NPC condition required")
    counts[0]+=1
    if counts[0]>MAX_NODES:
        raise NPCConditionalError("rule predicate complexity budget exceeded")
    if set(node)=={"all"} or set(node)=={"any"}:
        tag=next(iter(node))
        children=node[tag]
        if type(children) is not list or not 1<=len(children)<=6:
            raise NPCConditionalError("all/any requires one to six conditional clauses")
        return {tag:[_predicate(item,counts,depth+1) for item in children]}
    if set(node)=={"not"}:
        return {"not":_predicate(node["not"],counts,depth+1)}
    if set(node)=={"fact","op","value"}:
        if (type(node["fact"]) is not str or type(node["op"]) is not str or
            node["fact"] not in FACTS or node["op"] not in ("gte","lte","eq") or
            type(node["value"]) is not int or not 0<=node["value"]<=4096):
            raise NPCConditionalError("unreviewed or impossible original world fact")
        return dict(node)
    raise NPCConditionalError("unknown if/and/or/not clause schema")


def _rules(rules):
    if type(rules) not in (tuple,list) or not 1<=len(rules)<=MAX_RULES:
        raise NPCConditionalError("one to twelve original causal rules required")
    checked=[]
    seen=set()
    for item in rules:
        if (type(item) is not dict or set(item)!={"id","quest_id","when","do"} or
            type(item["id"]) is not str or not 1<=len(item["id"])<=32 or
            any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                for c in item["id"]) or item["id"] in seen or
            type(item["quest_id"]) is not int or not 0<=item["quest_id"]<=11 or
            item["do"] not in GOALS):
            raise NPCConditionalError("rules require unique source, quest and recognized original action")
        seen.add(item["id"])
        checked.append({
            "id":item["id"],"quest_id":item["quest_id"],
            "when":_predicate(item["when"],[0]),"do":item["do"]
        })
    return checked


def _facts(world,quest):
    site=next(s for s in world["sites"] if s["id"]==quest["site_id"])
    return {
        "source_eyewitnesses":len(quest["witnesses"]),
        "real_testimonies":len(quest["testimonies"]),
        "reported_rumors":len(quest["heard_from"]),
        "real_material_actions":quest["material_actions"],
        "site_integrity":site["integrity"],
        "player_supplies":world["supplies"],
        "player_stamina":world["stamina"],
        "world_tick":world["tick"],
        "quest_active":int(quest["status"]=="active"),
        "quest_support_chosen":int(quest["choice"]=="support"),
        "quest_exploit_chosen":int(quest["choice"]=="exploit"),
        "external_physical_origin":int(quest["origin_actor"]=="external:physics"),
    }


def _matches(node,facts):
    if "all" in node:
        return all(_matches(c,facts) for c in node["all"])
    if "any" in node:
        return any(_matches(c,facts) for c in node["any"])
    if "not" in node:
        return not _matches(node["not"],facts)
    val=facts[node["fact"]]
    if node["op"]=="gte":
        return val>=node["value"]
    if node["op"]=="lte":
        return val<=node["value"]
    return val==node["value"]


def run_npc_conditional_rules(episodes,scene,rules,world_settings=None,
                              *,mode="preview",authorized=False):
    if mode not in ("preview","commit") or type(mode) is not str:
        raise NPCConditionalError("only source-audited preview or commit mode exists")
    if mode=="commit" and authorized is not True:
        raise PermissionError("real NPC-world rule effects require explicit local operator action")
    checked=_rules(rules)
    try:
        world_cfg=make_editor_document("quest_director",world_settings)["settings"]
        working=deepcopy(list(episodes))
        original=run_episodic_physics_world(working,scene,world_cfg)
        verify_episodic_physics_world(original,working,scene,world_cfg)
        current=original
        ledger=[]
        previous=_digest({"schema":SCHEMA,"original":original["digest"],
                          "rules":checked,"mode":mode})
        used=0
        for rule in checked:
            q=next((quest for quest in current["world_state"]["quests"]
                    if quest["id"]==rule["quest_id"]),None)
            if q is None or q["origin_actor"]!="external:physics":
                raise NPCConditionalError("conditional rule cannot bind an unauthored source quest")
            facts=_facts(current["world_state"],q)
            accepted=_matches(rule["when"],facts)
            outcome="condition_false"
            navigated=None
            applied=False
            if accepted:
                if used>=MAX_APPLIED and mode=="commit":
                    outcome="reviewed_rule_effect_budget_exhausted"
                else:
                    nav=navigate_verified_investigation(
                        current,working,scene,world_cfg,
                        quest_id=rule["quest_id"],objective=rule["do"])
                    verify_investigation_navigation(
                        nav,current,working,scene,world_cfg)
                    navigated={
                        "route_digest":nav["digest"],
                        "outcome":nav["outcome"],
                        "commands":list(nav["planned_and_simulated_actions"]),
                        "source_quest_event":nav["original_quest_event"],
                        "target_npc":nav["target_npc_id"],
                    }
                    expected={
                        "testimony":"firsthand_testimony_recorded",
                        "repair":"real_site_repair_enacted",
                        "aid":"finite_original_community_aid_delivered",
                        "resolve":"original_quest_resolved",
                    }[rule["do"]]
                    if nav["outcome"]!=expected or not nav["planned_and_simulated_actions"]:
                        outcome="reviewed_route_cannot_earn_objective"
                    elif mode=="preview":
                        outcome="eligible_source_actions_preview_only"
                    else:
                        new=deepcopy(working)
                        cost=len(nav["planned_and_simulated_actions"])
                        total=current["total_world_actions"]
                        if (len(new[-1]["world_actions"])+cost>MAX_ACTIONS_PER_EPISODE or
                            total+cost>MAX_TOTAL_WORLD_ACTIONS):
                            outcome="finite_original_world_action_budget_exhausted"
                        else:
                            new[-1]["world_actions"].extend(
                                nav["planned_and_simulated_actions"])
                            # Reconstruct the entire original source history.
                            replay=run_episodic_physics_world(new,scene,world_cfg)
                            verify_episodic_physics_world(replay,new,scene,world_cfg)
                            if replay["world_state"]!=nav["end_world_state"]:
                                raise NPCConditionalError(
                                    "authoritative original quest world differs from simulated route")
                            current=replay
                            working=new
                            applied=True
                            used+=1
                            outcome="original_gameplay_actions_applied"
            event={
                "id":rule["id"],"quest_id":rule["quest_id"],"effect":rule["do"],
                "condition_satisfied":accepted,
                "verified_facts":facts,
                "route":navigated,
                "result":outcome,"applied":applied,
                "before_campaign_digest":original["digest"] if not ledger else ledger[-1]["after_campaign_digest"],
                "after_campaign_digest":current["digest"],
            }
            head=_digest({"previous":previous,"event":event})
            ledger.append({**event,"previous_hash":previous,"head_hash":head})
            previous=head
        result={
            "schema":SCHEMA,"mode":mode,
            "source_campaign_digest":original["digest"],
            "final_campaign_digest":current["digest"],
            "rules":checked,"rule_results":ledger,
            "applied_effects":used,
            "episodes":working if mode=="commit" else deepcopy(list(episodes)),
            "world_scene_digest":scene["digest"],
            "world_state":current["world_state"],
            "head_hash":previous,
            "source_game_files_mutated":False,
            "unearned_npc_rewards_granted":False,
            "automatic_ai_promotion_approved":False,
            "native_device_certified":False,
        }
    except NPCConditionalError:
        raise
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise NPCConditionalError(
            "typed original conditional world cannot reconstruct source effects") from exc
    return {**result,"digest":_digest(result)}


def verify_npc_conditional_rules(proof,episodes,scene,world_settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise NPCConditionalError("source-verified conditional world proof is missing")
    try:
        replay=run_npc_conditional_rules(
            episodes,scene,proof["rules"],world_settings,
            mode=proof["mode"],authorized=proof["mode"]=="commit")
    except (TypeError,KeyError) as exc:
        raise NPCConditionalError("conditional proof lacks source rule configuration") from exc
    if replay!=proof:
        raise NPCConditionalError("forged conditional facts, applied actions, quest or world reward")
    return True


__all__=["SCHEMA","MAX_RULES","MAX_NODES","MAX_DEPTH","MAX_APPLIED",
         "FACTS","GOALS","NPCConditionalError","run_npc_conditional_rules",
         "verify_npc_conditional_rules"]
