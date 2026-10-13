"""Adversarial what-if laboratory for genuinely replayed original world clocks.

Take identical independently verified physics/genre/NPC source inputs and
swap adjacent causal admissions. Re-execute EACH alternative using the
canonical engine; quantify changes in witnessed memories, rumor propagation,
quest outcomes and finite material inventories. Invalid timelines remain
explicitly invalid, never promoted as wins or counterfactual observations.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_interleaved_world import (
    InterleavedWorldError,run_interleaved_world,verify_interleaved_world,
)

SCHEMA="skeleton.game_builder.interleaved_counterfactual_lab.v1"
MAX_CANDIDATES=12
MAX_TIMELINE_LENGTH=96


class CounterfactualWorldError(ValueError):
    """Counterfactual original source, world time or replay claim rejected."""


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _snapshot(world):
    return {
        "event_origins":[(e["actor"],e["kind"],e["site_id"],e["tick"],
                          tuple(e["direct_witnesses"])) for e in world["events_log"]],
        "world_time":world["tick"],
        "player_cell":world["player"],
        "player_resources":{key:world[key] for key in
                            ("gold","supplies","stamina","reputation")},
        "site_integrity":[s["integrity"] for s in world["sites"]],
        "site_stock":[s["stock"] for s in world["sites"]],
        "direct_memory":[
            (npc["id"],tuple((m["event_id"],m["site_id"],m["kind"])
                              for m in npc["memories"]))
            for npc in world["npcs"]
        ],
        "rumor_memory":[
            (npc["id"],tuple((m["event_id"],m["site_id"],m["kind"])
                              for m in npc["heard"]))
            for npc in world["npcs"]
        ],
        "rumor_edge_count":len(world["rumor_edges"]),
        "npc_suspicion":[(n["id"],n["suspicion"]) for n in world["npcs"]],
        "npc_trust":[(n["id"],n["trust"]) for n in world["npcs"]],
        "quest_state":[
            (q["id"],q["origin_event"],q["status"],q["choice"],
             tuple(q["testimonies"]),q["material_actions"])
            for q in world["quests"]
        ],
        "quests_completed":world["quests_completed"],
        "quests_exploited":world["quests_exploited"],
        "terminal":(world["finished"],world["failed"],world["victory"]),
    }


def _changes(baseline,candidate):
    fields={}
    for name in baseline:
        if baseline[name]!=candidate[name]:
            fields[name]={
                "baseline":baseline[name],
                "counterfactual":candidate[name],
            }
    return fields


def _alternatives(timeline,baseline,max_candidates):
    """Stable adjacent swaps; all source-local chronological checks remain active."""
    # Signed executed durations, not speculative new engine time. For fixed
    # action durations canonical replay validates all constructed ticks.
    lengths=[receipt["world_tick"]-receipt["source_at"]
             for receipt in baseline["timeline"]]
    if len(lengths)!=len(timeline) or any(
            type(duration) is not int or duration<=0 for duration in lengths):
        raise CounterfactualWorldError("complete positive signed world-clock durations required")
    possibilities=[]
    for index in range(len(timeline)-1):
        left,right=timeline[index],timeline[index+1]
        if left["lane"]==right["lane"] and left.get("source_index")==right.get("source_index"):
            # No source-local time inversion, nor same-source NPC action
            # reversal (even if two commands happen to share a label).
            continue
        authored=[dict(x) for x in timeline]
        authored[index],authored[index+1]=authored[index+1],authored[index]
        swapped=list(lengths)
        swapped[index],swapped[index+1]=swapped[index+1],swapped[index]
        clock=0
        for item,duration in zip(authored,swapped):
            item["at"]=clock
            clock+=duration
        possibilities.append({
            "name":"adjacent_causal_swap",
            "original_positions":[index,index+1],
            "timeline":authored,
            "expected_duration_sum":clock,
        })
        if len(possibilities)>=max_candidates:
            break
    return possibilities


def run_counterfactual_lab(physical,genres,world_scene,timeline,
                           world_settings=None,*,max_candidates=8):
    if (type(max_candidates) is not int or not 1<=max_candidates<=MAX_CANDIDATES or
        type(timeline) not in (list,tuple) or
        not 2<=len(timeline)<=MAX_TIMELINE_LENGTH):
        raise CounterfactualWorldError("bounded source-world baseline and counterfactual budget required")
    try:
        original=run_interleaved_world(
            physical,genres,world_scene,timeline,world_settings)
        verify_interleaved_world(
            original,physical,genres,world_scene,timeline,world_settings)
        before=_snapshot(original["world_state"])
        variations=_alternatives(timeline,original,max_candidates)
        candidates=[]
        previous=_hash({
            "schema":SCHEMA,
            "baseline":original["digest"],
            "source_scene":world_scene["digest"],
            "max_candidates":max_candidates,
        })
        for index,plan in enumerate(variations):
            entry={
                "candidate_index":index,
                "strategy":plan["name"],
                "swapped_original_positions":plan["original_positions"],
                "authored_timeline":plan["timeline"],
                "baseline_digest":original["digest"],
            }
            try:
                executed=run_interleaved_world(
                    physical,genres,world_scene,plan["timeline"],world_settings)
                verify_interleaved_world(
                    executed,physical,genres,world_scene,plan["timeline"],
                    world_settings)
                after=_snapshot(executed["world_state"])
                differences=_changes(before,after)
                # Recorded difference count is not a "quality score". No
                # subjective or learned model promotion is inferred.
                entry.update({
                    "valid":True,
                    "outcome":"independently_replayed_source_world",
                    "candidate_digest":executed["digest"],
                    "candidate_head_hash":executed["head_hash"],
                    "actual_world_tick":executed["world_state"]["tick"],
                    "changed_dimensions":sorted(differences),
                    "changed_dimension_count":len(differences),
                    "verified_deltas":differences,
                    "actual_world_state_digest":_hash(executed["world_state"]),
                })
            except InterleavedWorldError:
                entry.update({
                    "valid":False,
                    "outcome":"invalid_source_or_world_chronology",
                    "candidate_digest":None,
                    "candidate_head_hash":None,
                    "actual_world_tick":None,
                    "changed_dimensions":[],
                    "changed_dimension_count":0,
                    "verified_deltas":{},
                    "actual_world_state_digest":None,
                })
            head=_hash({"previous":previous,"entry":entry})
            candidates.append({**entry,"previous_hash":previous,"head_hash":head})
            previous=head
        accepted=[c for c in candidates if c["valid"]]
        report={
            "schema":SCHEMA,
            "baseline_campaign_digest":original["digest"],
            "baseline_world_state_digest":_hash(original["world_state"]),
            "baseline_world_tick":original["world_state"]["tick"],
            "baseline_snapshot":before,
            "max_candidates":max_candidates,
            "candidates":candidates,
            "total_trials":len(candidates),
            "valid_replayed_trials":len(accepted),
            "invalid_trials":len(candidates)-len(accepted),
            "causally_changed_trials":sum(c["changed_dimension_count"]>0 for c in accepted),
            "head_hash":previous,
            "source_game_files_modified":False,
            "unearned_world_rewards_applied":False,
            "automatic_ai_weight_promotion":False,
            "native_full_world_certified":False,
        }
        return {**report,"digest":_hash(report)}
    except CounterfactualWorldError:
        raise
    except (InterleavedWorldError,ValueError,KeyError,TypeError,IndexError) as exc:
        raise CounterfactualWorldError(
            "baseline original source history is not independently executable"
        ) from exc


def verify_counterfactual_lab(proof,physical,genres,scene,timeline,
                              settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise CounterfactualWorldError("independent game counterfactual proof required")
    try:
        rerun=run_counterfactual_lab(
            physical,genres,scene,timeline,settings,
            max_candidates=proof["max_candidates"])
    except (KeyError,TypeError) as exc:
        raise CounterfactualWorldError("source-bound counterfactual proof lacks finite budget") from exc
    if proof!=rerun:
        raise CounterfactualWorldError("forged causal NPC effects, alternative chronology or improvement claims")
    return True


__all__=["SCHEMA","MAX_CANDIDATES","CounterfactualWorldError",
         "run_counterfactual_lab","verify_counterfactual_lab"]
