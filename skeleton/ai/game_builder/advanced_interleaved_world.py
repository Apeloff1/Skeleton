"""Deterministic event-level interleaving of verified original game engines.

Original platformer/racing/sandbox collisions, farming/sailing/flight earned
achievements and NPC-world actions are scheduled on ONE logical world clock.
Events cannot be omitted, duplicated, reordered inside a source, retrodated or
injected as rewards. The original genre simulations are verified separately:
this is event-level causality, NOT lockstep cross-engine frame simulation.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_physics_multi_incident_world import (
    run_multi_incident_world,verify_multi_incident_world,
)
from .advanced_genre_npc_event_bridge import (
    run_cross_genre_world,verify_cross_genre_world,
)
from .advanced_quest_director_runtime import (
    start as quest_start,apply_scene as quest_apply,step as quest_step,
    apply_verified_external_physical_incident,
    apply_verified_external_gameplay_event,
)
from .advanced_level_scenes import validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.interleaved_event_world.v1"
MAX_PHYSICAL_EPISODES=6
MAX_GENRE_SESSIONS=4
MAX_GENRE_EVENTS=8
MAX_WORLD_ACTIONS=64
MAX_TIMELINE_ENTRIES=96


class InterleavedWorldError(ValueError):
    """Source identity, ordering, signed world or causality mismatch."""


def _hash(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def _sources(physical,genres,scene,settings):
    """Pre-admit complete source evidence. No NPC state is accepted from it."""
    if (type(physical) not in (list,tuple) or
        not 1<=len(physical)<=MAX_PHYSICAL_EPISODES or
        type(genres) not in (list,tuple) or
        not 1<=len(genres)<=MAX_GENRE_SESSIONS):
        raise InterleavedWorldError("finite physical and original genre inputs required")
    physics=[]
    genre=[]
    identities=set()
    continuity={}
    for spec in physical:
        if (type(spec) is not dict or set(spec)!={
                "source_session","source_settings","physics_actions",
                "bindings","world_actions"} or spec["world_actions"]!=[]):
            raise InterleavedWorldError(
                "interleaving requires standalone physical episodes without preplayed world actions")
        source=spec["source_session"]
        if type(source) is not dict or type(source.get("actions")) is not list:
            raise InterleavedWorldError("original physics source transcript invalid")
        cfg=make_editor_document(source["editor"],spec["source_settings"])
        key=(source["editor"],source["scene"]["digest"],cfg["digest"])
        prefix=continuity.get(key)
        moves=source["actions"]
        if prefix is not None and (
            len(moves)<=len(prefix) or moves[:len(prefix)]!=prefix):
            raise InterleavedWorldError("physical source episodes must extend original session history")
        continuity[key]=list(moves)
        reviewed=run_multi_incident_world(
            source,scene,spec["source_settings"],settings,
            physics_actions=spec["physics_actions"],
            bindings=spec["bindings"],world_actions=())
        verify_multi_incident_world(
            reviewed,source,scene,spec["source_settings"],settings)
        if reviewed["interop_digest"] in identities:
            raise InterleavedWorldError("physical source collision receipt replayed")
        identities.add(reviewed["interop_digest"])
        physics.append(reviewed)
    total=0
    for spec in genres:
        if type(spec) is not dict or set(spec)!={
                "source_session","source_settings","bindings"}:
            raise InterleavedWorldError("exact original genre source mapping required")
        source=spec["source_session"]
        if type(source) is not dict or type(source.get("digest")) is not str:
            raise InterleavedWorldError("source genre game receipt missing")
        if source["digest"] in identities:
            raise InterleavedWorldError("original achievement session replayed")
        identities.add(source["digest"])
        reviewed=run_cross_genre_world(
            source,scene,spec["bindings"],spec["source_settings"],
            settings,world_actions=())
        verify_cross_genre_world(
            reviewed,source,scene,spec["source_settings"],settings)
        total+=len(reviewed["earned_events"])
        if total>MAX_GENRE_EVENTS:
            raise InterleavedWorldError("source-verified genre event capacity exceeded")
        genre.append(reviewed)
    return physics,genre


def run_interleaved_world(physical_episodes,genre_sessions,world_scene,
                          timeline,world_settings=None):
    if (type(timeline) not in (list,tuple) or
        not 1<=len(timeline)<=MAX_TIMELINE_ENTRIES):
        raise InterleavedWorldError("finite nonempty original world event schedule required")
    try:
        settings=make_editor_document("quest_director",world_settings)
        cfg=settings["settings"]
        scene=validate_advanced_scene(world_scene,cfg)
        physical,genres=_sources(
            physical_episodes,genre_sessions,world_scene,world_settings)
        world=quest_start(cfg,scene["seed"])
        quest_apply(world,cfg,scene["layout"])
        physical_next=[0]*len(physical)
        genre_next=[0]*len(genres)
        world_actions=0
        receipts=[]
        previous=_hash({
            "schema":SCHEMA,"world_scene":scene["digest"],
            "settings_digest":settings["digest"],
            "physical_sources":[p["digest"] for p in physical],
            "genre_sources":[g["digest"] for g in genres],
        })
        for position,item in enumerate(timeline):
            if type(item) is not dict or "lane" not in item or "at" not in item:
                raise InterleavedWorldError("typed authored source clock entry required")
            if type(item["at"]) is not int or item["at"]!=world["tick"]:
                raise InterleavedWorldError(
                    "source event clock must advance by actual previous NPC events")
            if world["finished"] or world["failed"]:
                raise InterleavedWorldError("terminal NPC world rejects further scheduled events")
            lane=item["lane"]
            source_identity=None
            if lane in ("physical","genre"):
                if (set(item)!={"at","lane","source_index","event_index"} or
                    type(item["source_index"]) is not int or
                    type(item["event_index"]) is not int):
                    raise InterleavedWorldError("exact original source/action event index required")
                index=item["source_index"]
                event_index=item["event_index"]
                if lane=="physical":
                    if not 0<=index<len(physical):
                        raise InterleavedWorldError("physical source episode not authenticated")
                    record=physical[index]
                    # Physical episodes preserve source episode order; genre
                    # actions may be interleaved in between these episodes.
                    if index>0 and any(
                            physical_next[j]!=len(physical[j]["incidents"])
                            for j in range(index)):
                        raise InterleavedWorldError("later physical episode cannot overtake earlier source")
                    cursor=physical_next
                    events=record["incidents"]
                    if event_index!=cursor[index] or event_index>=len(events):
                        raise InterleavedWorldError("physical source impact repeated or reordered")
                    hit=events[event_index]
                    receipt={
                        "interop_digest":record["interop_digest"],
                        "source_editor":record["source_editor"],
                        "source_id":hit["source_id"],
                    }
                    event=apply_verified_external_physical_incident(
                        world,cfg,hit["site_id"],receipt,
                        impact_severity=hit["severity"])
                    source_identity={
                        "source_receipt":record["digest"],
                        "first_tick":hit["physics_first_tick"],
                        "first_frame":hit["physics_first_frame"],
                        "source_id":hit["source_id"],
                        "real_contact_count":hit["real_contact_count"],
                    }
                else:
                    if not 0<=index<len(genres):
                        raise InterleavedWorldError("unapproved source genre session")
                    record=genres[index]
                    cursor=genre_next
                    events=record["earned_events"]
                    if event_index!=cursor[index] or event_index>=len(events):
                        raise InterleavedWorldError("genre event duplicated or inverted")
                    earned=events[event_index]
                    receipt={
                        "source_session_digest":record["source_session_digest"],
                        "source_editor":record["source_editor"],
                        "source_event":earned["source_event"],
                        "trace_index":earned["trace_index"],
                    }
                    event=apply_verified_external_gameplay_event(
                        world,cfg,earned["site_id"],receipt,earned["world_kind"])
                    source_identity={
                        "source_receipt":record["digest"],
                        "trace_digest":earned["original_trace_digest"],
                        "trace_index":earned["trace_index"],
                        "verified_event":earned["source_event"],
                        "real_stock":event["real_world_stock_transferred"],
                    }
                cursor[index]+=1
                source_identity["world_event_id"]=event["id"]
                source_identity["direct_witnesses"]=list(event["direct_witnesses"])
                source_identity["origin_quests"]=[
                    q["id"] for q in world["quests"]
                    if q["origin_event"]==event["id"]]
            elif lane=="world":
                if set(item)!={"at","lane","action"} or type(item["action"]) is not str:
                    raise InterleavedWorldError("only canonical original NPC actions may advance world")
                world_actions+=1
                if world_actions>MAX_WORLD_ACTIONS:
                    raise InterleavedWorldError("original world followup action budget exhausted")
                events=quest_step(world,cfg,item["action"])
                source_identity={"command":item["action"],
                                 "canonical_events":list(events)}
            else:
                raise InterleavedWorldError("unrecognized world schedule event lane")
            item_receipt={
                "position":position,"source_at":item["at"],
                "lane":lane,
                "source_index":item.get("source_index"),
                "event_index":item.get("event_index"),
                "source":source_identity,
                "world_tick":world["tick"],"world_turn":world["turn"],
                "site_integrity":[s["integrity"] for s in world["sites"]],
                "site_stock":[s["stock"] for s in world["sites"]],
                "active_quest_ids":[q["id"] for q in world["quests"]
                                    if q["status"]=="active"],
                "npc_direct_memory":[len(n["memories"]) for n in world["npcs"]],
                "rumor_edges":len(world["rumor_edges"]),
            }
            head=_hash({"previous":previous,"entry":item_receipt})
            receipts.append({**item_receipt,"previous_hash":previous,"head_hash":head})
            previous=head
        if (any(physical_next[i]!=len(p["incidents"])
                for i,p in enumerate(physical)) or
            any(genre_next[i]!=len(g["earned_events"])
                for i,g in enumerate(genres))):
            raise InterleavedWorldError("all independently earned source events must be scheduled once")
        report={
            "schema":SCHEMA,"world_scene_digest":scene["digest"],
            "world_settings_digest":settings["digest"],
            "physical_source_count":len(physical),
            "genre_source_count":len(genres),
            "authentic_physical_event_count":sum(len(p["incidents"]) for p in physical),
            "authentic_genre_event_count":sum(len(g["earned_events"]) for g in genres),
            "scheduled_world_actions":world_actions,
            "timeline":receipts,
            "world_state":world,"head_hash":previous,
            "original_projects_modified":False,
            "free_rewards_granted":False,
            "native_full_world_verified":False,
            "automatic_ai_weight_promotion":False,
        }
        return {**report,"digest":_hash(report)}
    except InterleavedWorldError:
        raise
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise InterleavedWorldError(
            "original source or authored event clock failed independent verification"
        ) from exc


def verify_interleaved_world(proof,physical,genres,scene,timeline,settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise InterleavedWorldError("source-authenticated world scheduler proof required")
    if run_interleaved_world(physical,genres,scene,timeline,settings)!=proof:
        raise InterleavedWorldError("world clock, testimony, source contact or reward forged")
    return True


__all__=["SCHEMA","MAX_PHYSICAL_EPISODES","MAX_GENRE_SESSIONS",
         "MAX_GENRE_EVENTS","MAX_WORLD_ACTIONS","MAX_TIMELINE_ENTRIES",
         "InterleavedWorldError","run_interleaved_world","verify_interleaved_world"]
