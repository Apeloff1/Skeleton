"""Independent adversarial counterfactuals for the same original game sources.

Rank genuinely replayed event orders under an explicit, narrow objective.
A ranking is NOT new model evidence or a universal measure of game quality:
it is the selected integer world metric for unchanged authenticated inputs.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json

from .advanced_interleaved_world import (
    run_interleaved_world,verify_interleaved_world,
    MAX_TIMELINE_ENTRIES,
)

SCHEMA="skeleton.game_builder.interleaved_counterfactual_mirror.v1"
MAX_SCENARIOS=6
OBJECTIVES=(
    "site_integrity","direct_memories","supplies","quests_completed",
)


class CounterfactualWorldError(ValueError):
    """Unreviewed scenario, changed original sources or forged improvement."""


def _hash(payload):
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _validate_scenarios(scenarios):
    if type(scenarios) not in (list,tuple) or not 2<=len(scenarios)<=MAX_SCENARIOS:
        raise CounterfactualWorldError("two to six original counterfactual schedules required")
    checked=[]
    names=set()
    world_actions=None
    for candidate in scenarios:
        if (type(candidate) is not dict or set(candidate)!={"name","timeline"} or
            type(candidate["name"]) is not str or
            not 1<=len(candidate["name"])<=32 or
            any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                for c in candidate["name"]) or candidate["name"] in names or
            type(candidate["timeline"]) not in (list,tuple) or
            not 1<=len(candidate["timeline"])<=MAX_TIMELINE_ENTRIES):
            raise CounterfactualWorldError("scenario must have unique bounded name and event clock")
        names.add(candidate["name"])
        commands=[]
        for entry in candidate["timeline"]:
            if type(entry) is not dict or not isinstance(entry.get("lane"),str):
                raise CounterfactualWorldError("original counterfactual clock entry missing")
            if entry["lane"]=="world":
                if type(entry.get("action")) is not str:
                    raise CounterfactualWorldError("world command must be original typed gameplay")
                commands.append(entry["action"])
        fingerprint=Counter(commands)
        if world_actions is None:
            world_actions=fingerprint
        elif fingerprint!=world_actions:
            raise CounterfactualWorldError(
                "counterfactual comparison must preserve actual NPC action multiset")
        checked.append({"name":candidate["name"],
                        "timeline":list(candidate["timeline"])})
    return checked


def _metrics(result):
    state=result["world_state"]
    sites=[site["integrity"] for site in state["sites"]]
    inventories=[site["stock"] for site in state["sites"]]
    eyewitness=sum(len(npc["memories"]) for npc in state["npcs"])
    rumors=sum(len(npc["heard"]) for npc in state["npcs"])
    return {
        "world_tick":state["tick"],"world_turn":state["turn"],
        "site_integrity":sites,
        "site_stock":inventories,
        "total_site_integrity":sum(sites),
        "direct_memories":eyewitness,
        "rumor_memories":rumors,
        "supplies":state["supplies"],
        "gold":state["gold"],
        "stamina":state["stamina"],
        "quests_completed":state["quests_completed"],
        "quests_exploited":state["quests_exploited"],
        "active_quests":sum(q["status"]=="active" for q in state["quests"]),
        "source_event_order":[
            {"lane":e["lane"],"source":e["source"].get(
                "verified_event",e["source"].get("source_id",e["source"].get("command"))),
             "world_tick":e["world_tick"]}
            for e in result["timeline"]],
        "npc_quest_origins":[
            {"id":q["id"],"actor":q["origin_actor"],
             "trigger":q["trigger"],"site_id":q["site_id"]}
            for q in state["quests"]],
        "terminal_finished":state["finished"],
        "terminal_failed":state["failed"],
    }


def _score(metric,objective):
    if objective=="site_integrity":
        return metric["total_site_integrity"]
    return metric[objective]


def run_interleaved_counterfactuals(physical,genres,world_scene,scenarios,
                                    world_settings=None,*,objective="site_integrity"):
    if type(objective) is not str or objective not in OBJECTIVES:
        raise CounterfactualWorldError("explicit bounded original world evaluation objective required")
    validated=_validate_scenarios(scenarios)
    reports=[]
    baseline=None
    previous=_hash({
        "schema":SCHEMA,"objective":objective,
        "names":[x["name"] for x in validated],
    })
    try:
        for index,scenario in enumerate(validated):
            proof=run_interleaved_world(
                physical,genres,world_scene,scenario["timeline"],world_settings)
            verify_interleaved_world(
                proof,physical,genres,world_scene,scenario["timeline"],world_settings)
            metrics=_metrics(proof)
            if index==0:
                baseline=metrics
            changes={
                "total_site_integrity":metrics["total_site_integrity"]-
                    baseline["total_site_integrity"],
                "direct_memories":metrics["direct_memories"]-baseline["direct_memories"],
                "supplies":metrics["supplies"]-baseline["supplies"],
                "gold":metrics["gold"]-baseline["gold"],
                "quests_completed":metrics["quests_completed"]-
                    baseline["quests_completed"],
                "world_ticks":metrics["world_tick"]-baseline["world_tick"],
                "event_order_changed":metrics["source_event_order"]!=
                    baseline["source_event_order"],
                "quest_origin_order_changed":metrics["npc_quest_origins"]!=
                    baseline["npc_quest_origins"],
            }
            entry={
                "scenario":scenario["name"],
                "original_timeline_digest":_hash(scenario["timeline"]),
                "verified_campaign_digest":proof["digest"],
                "full_world_head":proof["head_hash"],
                "metric":metrics,
                "objective_score":_score(metrics,objective),
                "difference_from_first":changes,
                "physical_event_count":proof["authentic_physical_event_count"],
                "genre_event_count":proof["authentic_genre_event_count"],
                "world_command_count":proof["scheduled_world_actions"],
            }
            head=_hash({"previous":previous,"counterfactual":entry})
            reports.append({**entry,"previous_hash":previous,"head_hash":head})
            previous=head
        if any(report["physical_event_count"]!=reports[0]["physical_event_count"] or
               report["genre_event_count"]!=reports[0]["genre_event_count"] or
               report["world_command_count"]!=reports[0]["world_command_count"]
               for report in reports):
            raise CounterfactualWorldError("counterfactuals do not compare the same authenticated inputs")
        ranking=sorted(reports,key=lambda x:(-x["objective_score"],x["scenario"]))
        result={
            "schema":SCHEMA,"objective":objective,
            "source_world_scene_digest":world_scene["digest"],
            "scenarios":reports,
            "ranking_for_this_metric_only":[
                {"rank":i+1,"scenario":v["scenario"],
                 "objective_score":v["objective_score"]}
                for i,v in enumerate(ranking)],
            "baseline_scenario":validated[0]["name"],
            "scenario_count":len(reports),"head_hash":previous,
            "original_project_mutated":False,
            "automatic_model_training_approved":False,
            "native_multi_engine_certified":False,
            "universal_game_quality_claimed":False,
        }
    except CounterfactualWorldError:
        raise
    except (ValueError,TypeError,KeyError,IndexError) as exc:
        raise CounterfactualWorldError(
            "counterfactual source event trace or actual original world replay rejected"
        ) from exc
    return {**result,"digest":_hash(result)}


def verify_interleaved_counterfactuals(proof,physical,genres,scene,scenarios,
                                       settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise CounterfactualWorldError("original signed counterfactual mirror required")
    try:
        independent=run_interleaved_counterfactuals(
            physical,genres,scene,scenarios,settings,objective=proof["objective"])
    except (TypeError,KeyError) as exc:
        raise CounterfactualWorldError("mirror lacks original metric source") from exc
    if independent!=proof:
        raise CounterfactualWorldError("scenario source, eyewitness, ranking or benefit was forged")
    return True


__all__=["SCHEMA","MAX_SCENARIOS","OBJECTIVES","CounterfactualWorldError",
         "run_interleaved_counterfactuals","verify_interleaved_counterfactuals"]
