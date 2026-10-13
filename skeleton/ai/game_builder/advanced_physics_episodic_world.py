"""Persistent episodic physics/NPC game campaign backed by real source replays.

Each episode is an independently reconstructed original game and physics
encounter. Distinct episodes share one actual 49-cell quest world: witness
positions, rumors, site integrity, supplies, quests and investigations persist.
Source gameplay progress is append-only per original scene. Neither repeating
an encounter nor reusing an older source transcript can mint new incidents.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_physics_multi_incident_world import (
    MultiIncidentError,run_multi_incident_world,verify_multi_incident_world,
)
from .advanced_quest_director_runtime import (
    start as quest_start,apply_scene as quest_apply,
    step as quest_step,apply_verified_external_physical_incident,
)
from .advanced_level_scenes import validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.episodic_physics_npc_world.v1"
MAX_EPISODES=6
MAX_ACTIONS_PER_EPISODE=24
MAX_TOTAL_WORLD_ACTIONS=64

class EpisodicWorldError(ValueError):
    """Episodic source, collision, NPC or playable quest history was rejected."""


def _digest(payload):
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def run_episodic_physics_world(episodes,quest_scene,quest_settings=None):
    if type(episodes) not in (list,tuple) or not 1<=len(episodes)<=MAX_EPISODES:
        raise EpisodicWorldError("one to six real source game episodes required")
    try:
        cfg=make_editor_document("quest_director",quest_settings)["settings"]
        original=validate_advanced_scene(quest_scene,cfg)
        world=quest_start(cfg,original["seed"])
        quest_apply(world,cfg,original["layout"])
        history=[]
        observed=set()
        continuity={}
        previous_hash=_digest({"schema":SCHEMA,"world":original["digest"],
                               "settings":make_editor_document(
                                   "quest_director",quest_settings)["digest"]})
        total_actions=0
        total_incidents=0
        for index,episode in enumerate(episodes):
            if type(episode) is not dict or set(episode)!={
                "source_session","source_settings","physics_actions",
                "bindings","world_actions"}:
                raise EpisodicWorldError("episode needs exact reviewed source, bindings and commands")
            source=episode["source_session"]
            if type(source) is not dict or type(source.get("actions")) is not list:
                raise EpisodicWorldError("signed source transcript must be a finite original-game list")
            transcript=source["actions"]
            settings=episode["source_settings"]
            source_key=(source["editor"],source["scene"]["digest"],
                        make_editor_document(source["editor"],settings)["digest"])
            prior=continuity.get(source_key)
            # A replayed identical source session cannot produce fresh NPC
            # events, even if the client supplies different physical inputs.
            if prior is not None and (
                len(transcript)<=len(prior) or transcript[:len(prior)]!=prior):
                raise EpisodicWorldError("original game progress must strictly extend prior source actions")
            if (type(episode["world_actions"]) not in (list,tuple)
                or len(episode["world_actions"])>MAX_ACTIONS_PER_EPISODE):
                raise EpisodicWorldError("episode investigation actions require a bounded array")
            total_actions+=len(episode["world_actions"])
            if total_actions>MAX_TOTAL_WORLD_ACTIONS:
                raise EpisodicWorldError("total authored investigation commands exceed world budget")
            # Independent replay and exact original-fixture custody.
            independent=run_multi_incident_world(
                source,quest_scene,settings,quest_settings,
                physics_actions=episode["physics_actions"],
                bindings=episode["bindings"],world_actions=())
            verify_multi_incident_world(
                independent,source,quest_scene,settings,quest_settings)
            identity=independent["interop_digest"]
            if identity in observed:
                raise EpisodicWorldError("physical encounter receipt replayed more than once")
            observed.add(identity)
            continuity[source_key]=list(transcript)
            played=[]
            for hit in independent["incidents"]:
                if world["finished"] or world["failed"]:
                    raise EpisodicWorldError("terminal original world rejects further physical incidents")
                signed={
                    "interop_digest":identity,
                    "source_editor":independent["source_editor"],
                    "source_id":hit["source_id"],
                }
                impact=apply_verified_external_physical_incident(
                    world,cfg,hit["site_id"],signed,
                    impact_severity=hit["severity"])
                quests=[q["id"] for q in world["quests"]
                        if q["origin_event"]==impact["id"]]
                played.append({
                    "physics_first_tick":hit["physics_first_tick"],
                    "physics_first_frame":hit["physics_first_frame"],
                    "original_fixture_index":hit["fixture_index"],
                    "source_id":hit["source_id"],
                    "source_type":hit["source_type"],
                    "site_id":hit["site_id"],
                    "contact_count":hit["real_contact_count"],
                    "severity":hit["severity"],
                    "real_world_event":impact,
                    "direct_witnesses":list(impact["direct_witnesses"]),
                    "quest_ids":quests,
                    "world_turn":world["turn"],
                    "world_tick":world["tick"],
                })
            sequence=[]
            for action in episode["world_actions"]:
                if world["finished"] or world["failed"]:
                    raise EpisodicWorldError("terminal quest world cannot accept further actions")
                events=quest_step(world,cfg,action)
                sequence.append({
                    "action":action,"world_turn":world["turn"],
                    "world_tick":world["tick"],"events":list(events),
                    "player_cell":world["player"],
                    "active_quests":[q["id"] for q in world["quests"]
                                     if q["status"]=="active"],
                    "completed_quests":world["quests_completed"],
                    "site_integrity":[s["integrity"] for s in world["sites"]],
                })
            receipt={
                "episode_index":index,"source_editor":source["editor"],
                "source_session_digest":source["digest"],
                "source_scene_digest":source["scene"]["digest"],
                "source_action_count":len(transcript),
                "interop_digest":identity,
                "physics_session_digest":independent["physics_session_digest"],
                "source_fixture_impacts":independent["source_fixture_impacts"],
                "applied_incidents":played,"investigation_turns":sequence,
                "world_tick":world["tick"],"world_turn":world["turn"],
                "world_site_integrity":[s["integrity"] for s in world["sites"]],
                "quests_completed":world["quests_completed"],
                "rumor_edges":len(world["rumor_edges"]),
            }
            head=_digest({"previous":previous_hash,"episode":receipt})
            history.append({**receipt,"previous_hash":previous_hash,
                            "head_hash":head})
            previous_hash=head
            total_incidents+=len(played)
        result={
            "schema":SCHEMA,"world_scene_digest":original["digest"],
            "episodes":history,"episode_count":len(history),
            "total_true_incidents":total_incidents,
            "total_world_actions":total_actions,
            "head_hash":previous_hash,
            "world_state":world,
            "original_source_games_unchanged":True,
            "auto_publication_approved":False,
            "native_hardware_certified":False,
            "automatic_ai_weight_promotion":False,
        }
    except EpisodicWorldError:
        raise
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise EpisodicWorldError(
            "original source episode, physics or NPC gameplay failed deterministic validation"
        ) from exc
    return {**result,"digest":_digest(result)}


def verify_episodic_physics_world(proof,episodes,quest_scene,quest_settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise EpisodicWorldError("signed episodic original-world gameplay proof required")
    replay=run_episodic_physics_world(episodes,quest_scene,quest_settings)
    if replay!=proof:
        raise EpisodicWorldError("episodic chronology, NPC memory, collision evidence or reward was forged")
    return True


__all__=["SCHEMA","MAX_EPISODES","MAX_ACTIONS_PER_EPISODE",
         "MAX_TOTAL_WORLD_ACTIONS","EpisodicWorldError",
         "run_episodic_physics_world","verify_episodic_physics_world"]
