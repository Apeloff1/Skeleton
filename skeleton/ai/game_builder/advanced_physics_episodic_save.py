"""Portable, fail-closed source-reconstructed saves for episodic NPC campaigns.

Persist only reviewed input records, not authoritative mutable memory. Import
replays every original genre session, physics encounter and quest-world action
and compares the independent campaign head/state; recomputing JSON hashes
alone never authorizes forged NPC testimony, original rewards or site repairs.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .advanced_physics_episodic_world import (
    MAX_EPISODES, MAX_ACTIONS_PER_EPISODE, MAX_TOTAL_WORLD_ACTIONS,
    run_episodic_physics_world, EpisodicWorldError,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.episodic_npc_save.v1"
MAX_SAVE_BYTES=2_000_000

class EpisodicSaveError(ValueError):
    """Malformed, altered, stale, oversized or unverifiable original save."""


def _canonical(document):
    return json.dumps(document,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False)


def _sha(document):
    return sha256(_canonical(document).encode("utf-8")).hexdigest()


def _bounded(document):
    try:
        size=len(_canonical(document).encode("utf-8"))
    except (TypeError,ValueError,OverflowError,RecursionError) as exc:
        raise EpisodicSaveError("episodic source save requires finite canonical JSON") from exc
    if size>MAX_SAVE_BYTES:
        raise EpisodicSaveError("source-authored episodic save exceeds 2 MB budget")
    return size


def export_episodic_savegame(episodes,scene,settings=None):
    try:
        world_rules=make_editor_document("quest_director",settings)
        reconstructed=run_episodic_physics_world(
            episodes,scene,world_rules["settings"])
        payload={
            "schema":SCHEMA,
            "format":"complete_source_replayed_physics_npc_actions",
            "world_scene":deepcopy(scene),
            "world_settings":world_rules["settings"],
            "world_settings_digest":world_rules["digest"],
            "episodes":deepcopy(list(episodes)),
            "episode_count":reconstructed["episode_count"],
            "total_world_actions":reconstructed["total_world_actions"],
            "head_hash":reconstructed["head_hash"],
            "campaign_digest":reconstructed["digest"],
            "world_state_digest":_sha(reconstructed["world_state"]),
            "original_game_saves_mutated":False,
            "automatic_promotion_approved":False,
            "native_device_certified":False,
            "requires_full_local_replay":True,
        }
        _bounded(payload)
        return {**payload,"digest":_sha(payload)}
    except EpisodicSaveError:
        raise
    except (EpisodicWorldError,KeyError,ValueError,TypeError) as exc:
        raise EpisodicSaveError("unverified original episodic campaign cannot be saved") from exc


def import_episodic_savegame(document):
    if type(document) is not dict:
        raise EpisodicSaveError("episodic save requires exact JSON object")
    _bounded(document)
    required={
        "schema","format","world_scene","world_settings","world_settings_digest",
        "episodes","episode_count","total_world_actions","head_hash",
        "campaign_digest","world_state_digest","original_game_saves_mutated",
        "automatic_promotion_approved","native_device_certified",
        "requires_full_local_replay","digest"
    }
    if (set(document)!=required or document.get("schema")!=SCHEMA or
        document["format"]!="complete_source_replayed_physics_npc_actions" or
        document["original_game_saves_mutated"] is not False or
        document["automatic_promotion_approved"] is not False or
        document["native_device_certified"] is not False or
        document["requires_full_local_replay"] is not True):
        raise EpisodicSaveError("unknown or falsely certified episodic save schema")
    if type(document["episodes"]) is not list or not 1<=len(document["episodes"])<=MAX_EPISODES:
        raise EpisodicSaveError("episodic save episode budget invalid")
    stripped={key:value for key,value in document.items() if key!="digest"}
    if _sha(stripped)!=document["digest"]:
        raise EpisodicSaveError("episodic source save was altered")
    try:
        source_rules=make_editor_document("quest_director",document["world_settings"])
        if source_rules["digest"]!=document["world_settings_digest"]:
            raise EpisodicSaveError("episodic world settings were not source authorized")
        campaign=run_episodic_physics_world(
            document["episodes"],document["world_scene"],source_rules["settings"])
        if (type(document["episode_count"]) is not int or
            type(document["total_world_actions"]) is not int or
            campaign["episode_count"]!=document["episode_count"] or
            campaign["total_world_actions"]!=document["total_world_actions"] or
            campaign["head_hash"]!=document["head_hash"] or
            campaign["digest"]!=document["campaign_digest"] or
            _sha(campaign["world_state"])!=document["world_state_digest"]):
            raise EpisodicSaveError("save cannot recreate original physical/NPC state")
    except EpisodicSaveError:
        raise
    except (EpisodicWorldError,KeyError,ValueError,TypeError) as exc:
        raise EpisodicSaveError("saved game source does not replay under original rules") from exc
    return {
        "verified":True,"save_digest":document["digest"],
        "episodes":deepcopy(document["episodes"]),
        "world_scene":deepcopy(document["world_scene"]),
        "world_settings":deepcopy(source_rules["settings"]),
        "campaign":campaign,
        "remaining_episode_budget":MAX_EPISODES-len(document["episodes"]),
        "remaining_action_budget":MAX_TOTAL_WORLD_ACTIONS-
                                  campaign["total_world_actions"],
        "external_source_code_executed":False,
        "automatic_publication_approved":False,
    }


def continue_episodic_savegame(document,*,additional_episodes=(),
                              additional_world_actions=()):
    """Resume real authored inputs only, never a client-submitted game state."""
    restored=import_episodic_savegame(document)
    if (type(additional_episodes) not in (list,tuple) or
        type(additional_world_actions) not in (list,tuple) or
        not additional_episodes and not additional_world_actions):
        raise EpisodicSaveError("continuation needs finite new episodes or world actions")
    episodes=deepcopy(restored["episodes"])
    if additional_world_actions:
        if (len(episodes[-1]["world_actions"])+len(additional_world_actions)>
            MAX_ACTIONS_PER_EPISODE or
            restored["campaign"]["total_world_actions"]+
                len(additional_world_actions)>MAX_TOTAL_WORLD_ACTIONS):
            raise EpisodicSaveError("original continuation world action capacity exhausted")
        if any(type(action) is not str for action in additional_world_actions):
            raise EpisodicSaveError("continuation must preserve exact original world actions")
        episodes[-1]["world_actions"].extend(additional_world_actions)
    if len(episodes)+len(additional_episodes)>MAX_EPISODES:
        raise EpisodicSaveError("no remaining episodic original game source capacity")
    episodes.extend(deepcopy(list(additional_episodes)))
    # No state injection: fully reconstruct the original plus new suffix.
    result=export_episodic_savegame(
        episodes,restored["world_scene"],restored["world_settings"])
    if result["episode_count"]<document["episode_count"]:
        raise EpisodicSaveError("continuation cannot roll back prior episodes")
    return result


__all__=["SCHEMA","MAX_SAVE_BYTES","EpisodicSaveError",
         "export_episodic_savegame","import_episodic_savegame",
         "continue_episodic_savegame"]
