"""Unified original physical incidents and independently earned genre events.

The original physical episode campaign is authoritatively reconstructed first.
Later signed farming/sailing/flight achievements enter THAT SAME world state:
NPC positions, memories, site stock/integrity and unfinished quests persist.
No duplicate session, trace index, impossible achievement or source-code write.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_physics_episodic_world import (
    run_episodic_physics_world,verify_episodic_physics_world,
)
from .advanced_genre_npc_event_bridge import (
    run_cross_genre_world,verify_cross_genre_world,
)
from .advanced_quest_director_runtime import (
    apply_verified_external_gameplay_event,
    step as quest_step,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.unified_genre_npc_campaign.v1"
MAX_GENRE_SESSIONS=4
MAX_TOTAL_GENRE_EVENTS=8
MAX_FOLLOWUP_ACTIONS=24

class UnifiedWorldError(ValueError):
    """Source game, physical event, genre achievement or world replay failed."""


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def run_unified_game_campaign(physical_episodes,genre_sessions,world_scene,
                              world_settings=None,*,world_actions=()):
    if (type(genre_sessions) not in (list,tuple) or
        not 1<=len(genre_sessions)<=MAX_GENRE_SESSIONS or
        type(world_actions) not in (list,tuple) or
        len(world_actions)>MAX_FOLLOWUP_ACTIONS or
        any(type(command) is not str for command in world_actions)):
        raise UnifiedWorldError("one to four finite original genre sessions and world commands required")
    try:
        cfg=make_editor_document("quest_director",world_settings)["settings"]
        base=run_episodic_physics_world(physical_episodes,world_scene,cfg)
        verify_episodic_physics_world(base,physical_episodes,world_scene,cfg)
        state=deepcopy(base["world_state"])
        observed_sessions=set()
        event_count=0
        previous=_hash({"schema":SCHEMA,"physical_campaign":base["digest"],
                        "world_scene":world_scene["digest"]})
        history=[]
        for index,source_spec in enumerate(genre_sessions):
            if (type(source_spec) is not dict or
                set(source_spec)!={"source_session","source_settings","bindings"}):
                raise UnifiedWorldError("genre addition requires exact original source and mapping")
            source=source_spec["source_session"]
            if type(source) is not dict:
                raise UnifiedWorldError("original genre session receipt missing")
            source_digest=source.get("digest")
            if type(source_digest) is not str or source_digest in observed_sessions:
                raise UnifiedWorldError("replayed original genre achievement cannot enter world twice")
            observed_sessions.add(source_digest)
            # Independently authenticate this exact original genre game and
            # trace-index event (in an isolated world), then use only its
            # verified source evidence to apply to the persistent real world.
            independent=run_cross_genre_world(
                source,world_scene,source_spec["bindings"],
                source_spec["source_settings"],cfg,world_actions=())
            verify_cross_genre_world(
                independent,source,world_scene,source_spec["source_settings"],cfg)
            event_count+=len(independent["earned_events"])
            if event_count>MAX_TOTAL_GENRE_EVENTS:
                raise UnifiedWorldError("cross-genre world event admission budget exhausted")
            signed_events=[]
            for earned in independent["earned_events"]:
                if state["finished"] or state["failed"]:
                    raise UnifiedWorldError("terminal world denies later original source achievements")
                source_receipt={
                    "source_session_digest":source_digest,
                    "source_editor":source["editor"],
                    "source_event":earned["source_event"],
                    "trace_index":earned["trace_index"],
                }
                applied=apply_verified_external_gameplay_event(
                    state,cfg,earned["site_id"],source_receipt,earned["world_kind"])
                quests=[quest["id"] for quest in state["quests"]
                        if quest["origin_event"]==applied["id"]]
                signed_events.append({
                    "trace_index":earned["trace_index"],
                    "original_action":earned["source_action"],
                    "source_event":earned["source_event"],
                    "original_trace_digest":earned["original_trace_digest"],
                    "original_source_id":source_digest,
                    "world_event":applied,
                    "direct_witnesses":list(applied["direct_witnesses"]),
                    "source_quest_ids":quests,
                    "real_stock_added":applied["real_world_stock_transferred"],
                    "world_tick":state["tick"],"world_turn":state["turn"],
                })
            entry={
                "original_genre_sequence":index,"original_editor":source["editor"],
                "source_session_digest":source_digest,
                "independent_genre_world_digest":independent["digest"],
                "source_scene_digest":independent["source_scene_digest"],
                "earned_events":signed_events,
                "world_tick":state["tick"],"world_turn":state["turn"],
                "site_inventory":[site["stock"] for site in state["sites"]],
                "site_integrity":[site["integrity"] for site in state["sites"]],
                "live_quests":[q["id"] for q in state["quests"]
                               if q["status"]=="active"],
            }
            head=_hash({"previous":previous,"source":entry})
            history.append({**entry,"previous_hash":previous,"head_hash":head})
            previous=head
        followup=[]
        for action in world_actions:
            if state["finished"] or state["failed"]:
                raise UnifiedWorldError("finished original living world rejects further actions")
            events=quest_step(state,cfg,action)
            step={
                "action":action,"tick":state["tick"],"turn":state["turn"],
                "events":list(events),
                "site_inventory":[site["stock"] for site in state["sites"]],
                "live_quests":[q["id"] for q in state["quests"]
                               if q["status"]=="active"],
            }
            head=_hash({"previous":previous,"followup":step})
            followup.append({**step,"previous_hash":previous,"head_hash":head})
            previous=head
        report={
            "schema":SCHEMA,"physical_campaign_digest":base["digest"],
            "world_scene_digest":world_scene["digest"],
            "physical_episode_count":base["episode_count"],
            "genre_session_count":len(genre_sessions),
            "verified_genre_event_count":event_count,
            "genre_history":history,
            "world_followup_history":followup,
            "world_state":state,
            "head_hash":previous,
            "original_game_files_mutated":False,
            "free_game_rewards_minted":False,
            "automatic_ai_weight_promotion":False,
            "native_device_certified":False,
        }
    except UnifiedWorldError:
        raise
    except (ValueError,TypeError,KeyError,IndexError) as exc:
        raise UnifiedWorldError(
            "original physical campaign or genre source could not independently replay"
        ) from exc
    return {**report,"digest":_hash(report)}


def verify_unified_game_campaign(proof,physical_episodes,genre_sessions,
                                 world_scene,world_settings=None,
                                 *,world_actions=()):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise UnifiedWorldError("verified cross-genre living-world campaign required")
    replay=run_unified_game_campaign(
        physical_episodes,genre_sessions,world_scene,world_settings,
        world_actions=world_actions)
    if replay!=proof:
        raise UnifiedWorldError("source chronology, source shipment, NPC testimony or game reward forged")
    return True


__all__=["SCHEMA","MAX_GENRE_SESSIONS","MAX_TOTAL_GENRE_EVENTS",
         "MAX_FOLLOWUP_ACTIONS","UnifiedWorldError",
         "run_unified_game_campaign","verify_unified_game_campaign"]
