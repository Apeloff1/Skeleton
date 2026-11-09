"""Portable, replay-verifiable original game savegames and continuations.

Savegame state is NOT trusted. On import, the complete session is regenerated
from original authored scene, typed settings and bounded inputs; arbitrary HP,
money, upgrades, positions, or fake completion flags cannot be imported.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping, Sequence

from .advanced_gameplay_runtime import (
    AdvancedRuntimeError, MAX_TURNS, run_advanced_session,
    verify_advanced_session,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.advanced_savegame.v1"
MAX_SAVE_BYTES=280_000


class SavegameError(AdvancedRuntimeError):
    """Portable original game save is stale, forged, malformed or oversized."""


def _canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False)


def _sha(payload):
    return sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _check_size(value):
    try:
        size=len(_canonical(value).encode("utf-8"))
    except (ValueError, TypeError, OverflowError) as exc:
        raise SavegameError("portable save is not canonical bounded JSON") from exc
    if size > MAX_SAVE_BYTES:
        raise SavegameError("portable game save exceeds explicit size budget")


def export_advanced_savegame(session: Mapping[str,object],
                             settings: Mapping[str,object]|None = None) -> dict:
    if type(session) is not dict:
        raise SavegameError("save requires an actual authoritative session receipt")
    rules=make_editor_document(session.get("editor"),settings)
    if not verify_advanced_session(session,rules["settings"]):
        raise SavegameError("session gameplay cannot be independently verified")
    record={
        "schema":SCHEMA,
        "editor":session["editor"],
        "seed":session["seed"],
        "settings":rules["settings"],
        "settings_digest":rules["digest"],
        "scene":session["scene"],
        "actions":list(session["actions"]),
        "session_digest":session["digest"],
        "head_digest":session["head_digest"],
        "turns":session["validated_turn_count"],
        "terminal":session["terminal"],
        "format":"complete_authoritative_action_log",
        "requires_local_replay_verification":True,
        "source_code_executed":False,
        "publication_approved":False,
    }
    _check_size(record)
    return {**record,"digest":_sha(record)}


def import_advanced_savegame(document: Mapping[str,object]) -> dict:
    _check_size(document)
    if type(document) is not dict or set(document)!={
        "schema","editor","seed","settings","settings_digest","scene",
        "actions","session_digest","head_digest","turns","terminal",
        "format","requires_local_replay_verification","source_code_executed",
        "publication_approved","digest"
    } or document.get("schema")!=SCHEMA:
        raise SavegameError("unknown savegame schema or unexpected state fields")
    stripped={k:v for k,v in document.items() if k!="digest"}
    if _sha(stripped)!=document["digest"]:
        raise SavegameError("portable savegame was tampered with")
    if document["format"]!="complete_authoritative_action_log" or (
        document["requires_local_replay_verification"] is not True
        or document["source_code_executed"] is not False
        or document["publication_approved"] is not False
    ):
        raise SavegameError("unverifiable or improperly certified savegame")
    if type(document["actions"]) is not list or len(document["actions"])>MAX_TURNS:
        raise SavegameError("saved action log exceeds available replay budget")
    configuration=make_editor_document(document["editor"],document["settings"])
    if configuration["digest"]!=document["settings_digest"]:
        raise SavegameError("savegame settings were changed after their review")
    replay=run_advanced_session(
        document["editor"],configuration["settings"],document["actions"],
        seed=document["seed"],scene=document["scene"])
    if (replay["digest"]!=document["session_digest"]
        or replay["head_digest"]!=document["head_digest"]
        or replay["validated_turn_count"]!=document["turns"]
        or replay["terminal"] is not document["terminal"]):
        raise SavegameError("savegame does not recreate the stored game state")
    return {"verified":True,"savegame_digest":document["digest"],
            "session":replay,"settings":configuration["settings"],
            "remaining_action_budget":MAX_TURNS-len(document["actions"]),
            "external_code_executed":False,"automatic_publication":False}


def continue_advanced_savegame(document: Mapping[str,object],
                               new_actions: Sequence[str]) -> dict:
    restored=import_advanced_savegame(document)
    if type(new_actions) not in (list,tuple) or not 1<=len(new_actions)<=MAX_TURNS:
        raise SavegameError("continuation must contain a bounded non-empty command batch")
    old=restored["session"]
    # "run" re-executes the entire prefix, not a client-submitted state blob.
    resumed=run_advanced_session(
        old["editor"],restored["settings"],list(old["actions"])+list(new_actions),
        seed=old["seed"],scene=old["scene"])
    return export_advanced_savegame(resumed,restored["settings"])


__all__=["SCHEMA","MAX_SAVE_BYTES","SavegameError",
         "export_advanced_savegame","import_advanced_savegame",
         "continue_advanced_savegame"]
