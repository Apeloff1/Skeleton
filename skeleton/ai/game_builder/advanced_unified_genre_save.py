"""Replay-only portable save for one physical and multi-genre NPC world.

A self-contained canonical input log: physical episodes, reviewed genre
achievements, original world scene, settings and later NPC actions. Never
trust player rewards, site stock, NPC memory, collision or quest state taken
from the saved JSON, even when its outer SHA-256 has been recomputed.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_unified_genre_campaign import (
    MAX_GENRE_SESSIONS,MAX_FOLLOWUP_ACTIONS,
    run_unified_game_campaign,UnifiedWorldError,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.unified_npc_source_save.v1"
MAX_SAVE_BYTES=3_000_000

class UnifiedSaveError(ValueError):
    """Saved mixed-source NPC campaign cannot be independently reconstructed."""


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False)


def _sha(value):
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _size(value):
    try:
        amount=len(_json(value).encode("utf-8"))
    except (TypeError,ValueError,RecursionError,OverflowError) as exc:
        raise UnifiedSaveError("untrusted mixed source game save must be finite canonical JSON") from exc
    if amount>MAX_SAVE_BYTES:
        raise UnifiedSaveError("original cross-genre game save exceeds finite 3 MB budget")
    return amount


def export_unified_world_save(physical_episodes,genre_sessions,world_scene,
                              world_settings=None,*,world_actions=()):
    try:
        settings=make_editor_document("quest_director",world_settings)
        replay=run_unified_game_campaign(
            physical_episodes,genre_sessions,world_scene,settings["settings"],
            world_actions=world_actions)
        payload={
            "schema":SCHEMA,
            "format":"complete_physics_and_genre_source_action_log",
            "physical_episodes":deepcopy(list(physical_episodes)),
            "genre_sessions":deepcopy(list(genre_sessions)),
            "world_scene":deepcopy(world_scene),
            "world_settings":deepcopy(settings["settings"]),
            "world_settings_digest":settings["digest"],
            "world_actions":deepcopy(list(world_actions)),
            "physical_episode_count":replay["physical_episode_count"],
            "genre_session_count":replay["genre_session_count"],
            "genre_event_count":replay["verified_genre_event_count"],
            "source_physical_campaign_digest":replay["physical_campaign_digest"],
            "campaign_digest":replay["digest"],
            "head_hash":replay["head_hash"],
            "world_state_digest":_sha(replay["world_state"]),
            "strict_source_replay_required":True,
            "original_game_files_modified":False,
            "native_device_certified":False,
            "automatic_publication_approved":False,
            "learning_weight_promotion_approved":False,
        }
        _size(payload)
        return {**payload,"digest":_sha(payload)}
    except UnifiedSaveError:
        raise
    except (TypeError,ValueError,KeyError,IndexError) as exc:
        raise UnifiedSaveError("combined source game cannot be safely saved") from exc


def import_unified_world_save(document):
    if type(document) is not dict:
        raise UnifiedSaveError("mixed game requires exact source replay document")
    _size(document)
    required={
        "schema","format","physical_episodes","genre_sessions",
        "world_scene","world_settings","world_settings_digest",
        "world_actions","physical_episode_count","genre_session_count",
        "genre_event_count","source_physical_campaign_digest",
        "campaign_digest","head_hash","world_state_digest",
        "strict_source_replay_required","original_game_files_modified",
        "native_device_certified","automatic_publication_approved",
        "learning_weight_promotion_approved","digest",
    }
    if (set(document)!=required or document.get("schema")!=SCHEMA or
        document["format"]!="complete_physics_and_genre_source_action_log" or
        document["strict_source_replay_required"] is not True or
        document["original_game_files_modified"] is not False or
        document["native_device_certified"] is not False or
        document["automatic_publication_approved"] is not False or
        document["learning_weight_promotion_approved"] is not False):
        raise UnifiedSaveError("unknown mixed game format or false source certification")
    if (_sha({k:v for k,v in document.items() if k!="digest"})!=document["digest"]):
        raise UnifiedSaveError("source authoring document checksum does not match")
    if (type(document["genre_sessions"]) is not list or
        not 1<=len(document["genre_sessions"])<=MAX_GENRE_SESSIONS or
        type(document["physical_episodes"]) is not list or
        type(document["world_actions"]) is not list or
        len(document["world_actions"])>MAX_FOLLOWUP_ACTIONS):
        raise UnifiedSaveError("source session or followup bounded input schema incorrect")
    try:
        settings=make_editor_document("quest_director",document["world_settings"])
        if settings["digest"]!=document["world_settings_digest"]:
            raise UnifiedSaveError("world settings source receipt mismatches authored settings")
        replay=run_unified_game_campaign(
            document["physical_episodes"],document["genre_sessions"],
            document["world_scene"],settings["settings"],
            world_actions=document["world_actions"])
        if (type(document["physical_episode_count"]) is not int or
            type(document["genre_session_count"]) is not int or
            type(document["genre_event_count"]) is not int or
            replay["physical_episode_count"]!=document["physical_episode_count"] or
            replay["genre_session_count"]!=document["genre_session_count"] or
            replay["verified_genre_event_count"]!=document["genre_event_count"] or
            replay["physical_campaign_digest"]!=document["source_physical_campaign_digest"] or
            replay["digest"]!=document["campaign_digest"] or
            replay["head_hash"]!=document["head_hash"] or
            _sha(replay["world_state"])!=document["world_state_digest"]):
            raise UnifiedSaveError("original physical/genre NPC world state cannot replay")
    except UnifiedSaveError:
        raise
    except (ValueError,TypeError,KeyError,IndexError) as exc:
        raise UnifiedSaveError("original source evidence, NPC memory or campaign tampered") from exc
    return {
        "verified":True,"save_digest":document["digest"],
        "physical_episodes":deepcopy(document["physical_episodes"]),
        "genre_sessions":deepcopy(document["genre_sessions"]),
        "world_actions":deepcopy(document["world_actions"]),
        "world_scene":deepcopy(document["world_scene"]),
        "world_settings":deepcopy(settings["settings"]),
        "replayed_campaign":replay,
        "remaining_genre_sessions":MAX_GENRE_SESSIONS-len(document["genre_sessions"]),
        "remaining_world_actions":MAX_FOLLOWUP_ACTIONS-len(document["world_actions"]),
        "original_source_files_modified":False,
        "automatic_publication":False,
    }


def continue_unified_world_save(document,*,new_genre_sessions=(),
                                new_world_actions=()):
    restored=import_unified_world_save(document)
    if (type(new_genre_sessions) not in (list,tuple) or
        type(new_world_actions) not in (list,tuple) or
        not new_genre_sessions and not new_world_actions):
        raise UnifiedSaveError("recovery requires finite new source sessions or world actions")
    if (new_genre_sessions and restored["world_actions"]):
        # Genre events are applied before world followups. Inserting them
        # behind already-played actions would rewrite causal NPC history.
        raise UnifiedSaveError(
            "cannot insert old genre achievements before already executed NPC followups")
    genres=deepcopy(restored["genre_sessions"])
    if len(genres)+len(new_genre_sessions)>MAX_GENRE_SESSIONS:
        raise UnifiedSaveError("source genre session budget exhausted")
    genres.extend(deepcopy(list(new_genre_sessions)))
    commands=deepcopy(restored["world_actions"])
    if len(commands)+len(new_world_actions)>MAX_FOLLOWUP_ACTIONS:
        raise UnifiedSaveError("verified original NPC-world action budget exhausted")
    if any(type(a) is not str for a in new_world_actions):
        raise UnifiedSaveError("unregistered nonstring original world action input")
    commands.extend(list(new_world_actions))
    return export_unified_world_save(
        restored["physical_episodes"],genres,
        restored["world_scene"],restored["world_settings"],
        world_actions=commands)


__all__=["SCHEMA","MAX_SAVE_BYTES","UnifiedSaveError",
         "export_unified_world_save","import_unified_world_save",
         "continue_unified_world_save"]
