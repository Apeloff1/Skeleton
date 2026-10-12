"""Counterfactual game-world laboratory with *real* source-replayed outcomes.

Compare alternate event orders while holding all original engine sources and
the EXACT same multiset of original NPC gameplay commands fixed. Never
fabricate an incident, testimony, resource or reward. Pairwise dominance is
reported only over explicit objective axes; tradeoffs are not fake victories.
This is a finite, operator-invoked deterministic gameplay preview, not model
training, unattended search or a native game certification.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_interleaved_world import (
    run_interleaved_world,verify_interleaved_world,
    MAX_TIMELINE_ENTRIES,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.event_world_whatif.v1"
MAX_SCENARIOS=8
# All dimensions must describe objectively observed reference-world state.
# Higher is preferable only WITHIN these explicitly named authoring goals;
# source event truth and causal-world constraints are never scored away.
AXES=(
    "quests_completed","remaining_site_integrity","site_stock",
    "player_supplies","player_stamina","player_gold",
    "player_reputation","firsthand_memories","trust_total",
    "inverse_suspicion","inverse_exploited_quests","survival",
)
METRICS=AXES+(
    "active_quests","expired_quests","rumor_records","rumor_edges",
    "world_tick","physical_events","genre_events","world_actions",
)


class WorldWhatIfError(ValueError):
    """Unfair, forged, incomplete or unaudited original-world comparison."""


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _canon_schedule(schedule):
    if type(schedule) is not list or not 1<=len(schedule)<=MAX_TIMELINE_ENTRIES:
        raise WorldWhatIfError("original world schedule must be a finite nonempty list")
    return _hash(schedule)


def _equivalence_key(timeline):
    """Counts *inputs* only, not a client-provided claimed replay result."""
    items=[]
    for e in timeline:
        if type(e) is not dict:
            raise WorldWhatIfError("source-world action entries must be typed objects")
        if e.get("lane")=="world" and set(e)=={"at","lane","action"}:
            if type(e["action"]) is not str:
                raise WorldWhatIfError("original-world command must be a string")
            items.append(("world",e["action"]))
        elif e.get("lane") in ("physical","genre") and set(e)=={
                "at","lane","source_index","event_index"}:
            if type(e["source_index"]) is not int or type(e["event_index"]) is not int:
                raise WorldWhatIfError("typed authentic source event IDs required")
            items.append((e["lane"],e["source_index"],e["event_index"]))
        else:
            raise WorldWhatIfError("unregistered event scheduling instruction")
    return sorted(items,key=lambda x:_hash(x))


def _metrics(proof):
    world=proof["world_state"]
    npc=world["npcs"]
    quests=world["quests"]
    return {
        "quests_completed":world["quests_completed"],
        "remaining_site_integrity":sum(site["integrity"] for site in world["sites"]),
        "site_stock":sum(site["stock"] for site in world["sites"]),
        "player_supplies":world["supplies"],
        "player_stamina":world["stamina"],
        "player_gold":world["gold"],
        "player_reputation":world["reputation"],
        "firsthand_memories":sum(len(n["memories"]) for n in npc),
        "trust_total":sum(n["trust"] for n in npc),
        "inverse_suspicion":-sum(n["suspicion"] for n in npc),
        "inverse_exploited_quests":-world["quests_exploited"],
        "survival":int(not world["failed"]),
        "active_quests":sum(q["status"]=="active" for q in quests),
        "expired_quests":sum(q["status"]=="expired" for q in quests),
        "rumor_records":sum(len(n["heard"]) for n in npc),
        "rumor_edges":len(world["rumor_edges"]),
        "world_tick":world["tick"],
        "physical_events":proof["authentic_physical_event_count"],
        "genre_events":proof["authentic_genre_event_count"],
        "world_actions":proof["scheduled_world_actions"],
    }


def _dominates(a,b,axes):
    return (all(a[x]>=b[x] for x in axes)
            and any(a[x]>b[x] for x in axes))


def run_world_whatif_lab(physical,genres,scene,scenarios,settings=None,
                         *,axes=AXES):
    if type(scenarios) not in (list,tuple) or not 2<=len(scenarios)<=MAX_SCENARIOS:
        raise WorldWhatIfError("compare two to eight genuine game-world timelines")
    if (type(axes) not in (list,tuple) or
        not 1<=len(axes)<=len(AXES) or
        any(type(x) is not str or x not in AXES for x in axes) or
        len(set(axes))!=len(axes)):
        raise WorldWhatIfError("choose distinct reviewed comparable gameplay outcomes")
    selected=tuple(axes)
    identifiers=set()
    invariant=None
    for item in scenarios:
        if (type(item) is not dict or set(item)!={"id","timeline"} or
            type(item["id"]) is not str or
            not 1<=len(item["id"])<=32 or
            any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                for ch in item["id"]) or item["id"] in identifiers):
            raise WorldWhatIfError("scenario IDs must be unique bounded source labels")
        identifiers.add(item["id"])
        timeline=item["timeline"]
        signature=_equivalence_key(timeline)
        if invariant is None:
            invariant=signature
        elif signature!=invariant:
            raise WorldWhatIfError(
                "alternate schedules must include exactly the same source events and NPC actions")
    try:
        world_cfg=make_editor_document("quest_director",settings)
        original=[]
        for index,item in enumerate(scenarios):
            # The canonical scheduler independently reconstructs and verifies
            # all original games, physics fixture IDs, genre achievements,
            # NPC memory/rumor causal rules and finite player actions.
            report=run_interleaved_world(
                physical,genres,scene,item["timeline"],world_cfg["settings"])
            verify_interleaved_world(
                report,physical,genres,scene,item["timeline"],world_cfg["settings"])
            original.append({
                "id":item["id"],"index":index,
                "schedule_digest":_canon_schedule(item["timeline"]),
                "world_receipt_digest":report["digest"],
                "world_head_hash":report["head_hash"],
                "metrics":_metrics(report),
                "source_event_order":[{
                    "lane":e["lane"],
                    "source_index":e["source_index"],
                    "event_index":e["event_index"],
                    "world_tick":e["world_tick"],
                    "origin":deepcopy(e["source"]),
                    "active_quest_ids":list(e["active_quest_ids"]),
                    "rumor_edges":e["rumor_edges"],
                } for e in report["timeline"]],
                "world_event_origins":[{
                    "id":event["id"],"actor":event["actor"],
                    "kind":event["kind"],"tick":event["tick"],
                    "site_id":event["site_id"],
                    "direct_witnesses":list(event["direct_witnesses"]),
                } for event in report["world_state"]["events_log"]],
            })
        baseline=original[0]["metrics"]
        candidates=[]
        for row in original:
            deltas={key:row["metrics"][key]-baseline[key] for key in METRICS}
            candidates.append({
                **row,
                "delta_from_baseline":deltas,
                "improved_axes":[axis for axis in selected if deltas[axis]>0],
                "regressed_axes":[axis for axis in selected if deltas[axis]<0],
                "changed_world_event_order":(
                    row["world_event_origins"]!=original[0]["world_event_origins"]
                ),
            })
        frontier=[a["index"] for a in candidates
                  if not any(_dominates(b["metrics"],a["metrics"],selected)
                             for b in candidates if b["index"]!=a["index"])]
        baseline_beaters=[
            row["index"] for row in candidates[1:]
            if _dominates(row["metrics"],baseline,selected)
        ]
        result={
            "schema":SCHEMA,
            "world_scene_digest":scene["digest"],
            "world_settings_digest":world_cfg["digest"],
            "baseline_id":original[0]["id"],
            "selected_axes":list(selected),
            "same_source_and_action_inputs":True,
            "scenarios":candidates,
            "pareto_frontier_indices":frontier,
            "strict_baseline_dominators":baseline_beaters,
            "authoritative_source_session_count":len(physical)+len(genres),
            "comparison_has_no_automatic_winner":True,
            "original_game_saves_unchanged":True,
            "automatic_model_training_approved":False,
            "native_full_campaign_certified":False,
        }
        return {**result,"digest":_hash(result)}
    except WorldWhatIfError:
        raise
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise WorldWhatIfError(
            "source-authenticated counterfactual original world cannot independently replay"
        ) from exc


def verify_world_whatif_lab(proof,physical,genres,scene,scenarios,settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise WorldWhatIfError("audited original-world counterfactual proof required")
    try:
        replay=run_world_whatif_lab(
            physical,genres,scene,scenarios,settings,
            axes=proof["selected_axes"])
    except (TypeError,KeyError) as exc:
        raise WorldWhatIfError("scenario selected axes or source proof unavailable") from exc
    if replay!=proof:
        raise WorldWhatIfError("comparison score, witnessed event or source-game outcome forged")
    return True


__all__=["SCHEMA","MAX_SCENARIOS","AXES","METRICS",
         "WorldWhatIfError","run_world_whatif_lab","verify_world_whatif_lab"]
