"""Replay-only portable saves for an interleaved original game-world clock.

Stores an exact authored source input log and logical clock, not mutable NPC
memory, gold, item inventory, physics collision claims or quest state. Restore
requires full independent original game/Physics/genre/world replay. A digest
is deterministic evidence identity, not an author signature.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_interleaved_world import (
    run_interleaved_world,verify_interleaved_world,
    MAX_PHYSICAL_EPISODES,MAX_GENRE_SESSIONS,MAX_TIMELINE_ENTRIES,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.interleaved_world_save.v1"
MAX_SAVE_BYTES=4_000_000


class InterleavedSaveError(ValueError):
    """Saved original world clock cannot be safely and exactly reconstructed."""


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=True)


def _digest(value):
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bounded(value):
    try:
        length=len(_canonical(value).encode("utf-8"))
    except (ValueError,TypeError,OverflowError,RecursionError) as exc:
        raise InterleavedSaveError("finite canonical original game save required") from exc
    if length>MAX_SAVE_BYTES:
        raise InterleavedSaveError("original interleaved source save exceeds four megabytes")
    return length


def export_interleaved_save(physical_episodes,genre_sessions,scene,timeline,
                            settings=None):
    try:
        cfg=make_editor_document("quest_director",settings)
        result=run_interleaved_world(
            physical_episodes,genre_sessions,scene,timeline,cfg["settings"])
        verify_interleaved_world(
            result,physical_episodes,genre_sessions,scene,timeline,cfg["settings"])
        payload={
            "schema":SCHEMA,"format":"complete_original_interleaved_source_log",
            "physical_episodes":deepcopy(list(physical_episodes)),
            "genre_sessions":deepcopy(list(genre_sessions)),
            "world_scene":deepcopy(scene),
            "world_settings":deepcopy(cfg["settings"]),
            "world_settings_digest":cfg["digest"],
            "timeline":deepcopy(list(timeline)),
            "physical_source_count":result["physical_source_count"],
            "genre_source_count":result["genre_source_count"],
            "true_physics_event_count":result["authentic_physical_event_count"],
            "true_genre_event_count":result["authentic_genre_event_count"],
            "world_actions":result["scheduled_world_actions"],
            "world_tick":result["world_state"]["tick"],
            "campaign_digest":result["digest"],
            "source_head_hash":result["head_hash"],
            "actual_world_state_digest":_digest(result["world_state"]),
            "replay_required":True,
            "original_project_files_mutated":False,
            "native_all_genres_certified":False,
            "automatic_publication_approved":False,
            "automatic_ai_weights_promotion":False,
        }
        _bounded(payload)
        return {**payload,"digest":_digest(payload)}
    except InterleavedSaveError:
        raise
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise InterleavedSaveError(
            "original source achievements or NPC world did not qualify for persistence"
        ) from exc


def import_interleaved_save(document):
    if type(document) is not dict:
        raise InterleavedSaveError("original interleaved save must be an exact object")
    _bounded(document)
    expected={
        "schema","format","physical_episodes","genre_sessions",
        "world_scene","world_settings","world_settings_digest","timeline",
        "physical_source_count","genre_source_count","true_physics_event_count",
        "true_genre_event_count","world_actions","world_tick","campaign_digest",
        "source_head_hash","actual_world_state_digest","replay_required",
        "original_project_files_mutated","native_all_genres_certified",
        "automatic_publication_approved","automatic_ai_weights_promotion","digest",
    }
    if (set(document)!=expected or document.get("schema")!=SCHEMA or
        document["format"]!="complete_original_interleaved_source_log" or
        document["replay_required"] is not True or
        document["original_project_files_mutated"] is not False or
        document["native_all_genres_certified"] is not False or
        document["automatic_publication_approved"] is not False or
        document["automatic_ai_weights_promotion"] is not False):
        raise InterleavedSaveError("unknown or falsely certified original world source save")
    if (_digest({k:v for k,v in document.items() if k!="digest"})
            !=document["digest"]):
        raise InterleavedSaveError("saved original game source checksum does not match")
    if (type(document["physical_episodes"]) is not list or
        not 1<=len(document["physical_episodes"])<=MAX_PHYSICAL_EPISODES or
        type(document["genre_sessions"]) is not list or
        not 1<=len(document["genre_sessions"])<=MAX_GENRE_SESSIONS or
        type(document["timeline"]) is not list or
        not 1<=len(document["timeline"])<=MAX_TIMELINE_ENTRIES):
        raise InterleavedSaveError("original game source collections exceed finite limits")
    try:
        cfg=make_editor_document("quest_director",document["world_settings"])
        if cfg["digest"]!=document["world_settings_digest"]:
            raise InterleavedSaveError("world source settings digest mismatches")
        result=run_interleaved_world(
            document["physical_episodes"],document["genre_sessions"],
            document["world_scene"],document["timeline"],cfg["settings"])
        verify_interleaved_world(
            result,document["physical_episodes"],document["genre_sessions"],
            document["world_scene"],document["timeline"],cfg["settings"])
        measurements={
            "physical_source_count":result["physical_source_count"],
            "genre_source_count":result["genre_source_count"],
            "true_physics_event_count":result["authentic_physical_event_count"],
            "true_genre_event_count":result["authentic_genre_event_count"],
            "world_actions":result["scheduled_world_actions"],
            "world_tick":result["world_state"]["tick"],
        }
        if any(type(document[key]) is not int or document[key]!=value
               for key,value in measurements.items()):
            raise InterleavedSaveError("original source event counts or final world clock forged")
        if (document["campaign_digest"]!=result["digest"] or
            document["source_head_hash"]!=result["head_hash"] or
            document["actual_world_state_digest"]!=_digest(result["world_state"])):
            raise InterleavedSaveError("original NPC testimony, resources or source chronology altered")
    except InterleavedSaveError:
        raise
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise InterleavedSaveError(
            "imported original game sessions cannot independently replay"
        ) from exc
    return {
        "verified":True,"save_digest":document["digest"],
        "physical_episodes":deepcopy(document["physical_episodes"]),
        "genre_sessions":deepcopy(document["genre_sessions"]),
        "world_scene":deepcopy(document["world_scene"]),
        "world_settings":deepcopy(cfg["settings"]),
        "timeline":deepcopy(document["timeline"]),
        "replayed_world":result,
        "remaining_timeline_entries":MAX_TIMELINE_ENTRIES-len(document["timeline"]),
        "source_projects_mutated":False,
        "native_all_genres_certified":False,
    }


def continue_interleaved_save(document,*,additional_physical=(),
                              additional_genre=(),additional_timeline=()):
    previous=import_interleaved_save(document)
    if (type(additional_physical) not in (tuple,list) or
        type(additional_genre) not in (tuple,list) or
        type(additional_timeline) not in (tuple,list) or
        not additional_physical and not additional_genre and not additional_timeline):
        raise InterleavedSaveError("finite appended original source events required")
    physics=deepcopy(previous["physical_episodes"])
    genre=deepcopy(previous["genre_sessions"])
    timeline=deepcopy(previous["timeline"])
    if (len(physics)+len(additional_physical)>MAX_PHYSICAL_EPISODES or
        len(genre)+len(additional_genre)>MAX_GENRE_SESSIONS or
        len(timeline)+len(additional_timeline)>MAX_TIMELINE_ENTRIES):
        raise InterleavedSaveError("original source capacity or world clock exhausted")
    physics.extend(deepcopy(list(additional_physical)))
    genre.extend(deepcopy(list(additional_genre)))
    timeline.extend(deepcopy(list(additional_timeline)))
    # The existing replay-valid prefix is never removed or changed.
    # Newly added source events may only appear at or after that world tick.
    # Full replay validates all new event indices, duplicates and source order.
    return export_interleaved_save(
        physics,genre,previous["world_scene"],timeline,
        previous["world_settings"])


__all__=["SCHEMA","MAX_SAVE_BYTES","InterleavedSaveError",
         "export_interleaved_save","import_interleaved_save",
         "continue_interleaved_save"]
