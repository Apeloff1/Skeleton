"""Segmented original roguelike campaigns: long-running, verified and resumable.

Unlike the bounded 128-action interactive reference API, this opt-in runner
supports thousands of original game commands, with independently recreatable
checkpoints. A submitted checkpoint is NEVER trusted as executable state;
continuation reconstructs it from the original scene and entire action history.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_roguelike_runtime import (
    RoguelikeActionError,ACTIONS,start,apply_scene,step,
)
from .advanced_level_scenes import validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.roguelike_longrun.v1"
MAX_COMMANDS=8192
DEFAULT_CHECKPOINT=64


class RoguelikeLongrunError(ValueError):
    """Illegal longrun transcript, unsupported custody or terminal continuation."""


def _json(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False)


def _digest(data):
    return sha256(_json(data).encode("utf-8")).hexdigest()


def _bound_actions(actions):
    if type(actions) not in (list,tuple) or len(actions)>MAX_COMMANDS or any(
        type(action) is not str or action not in ACTIONS for action in actions):
        raise RoguelikeLongrunError("longrun actions must be bounded and registered")


def replay_long_roguelike(settings=None,actions=(),*,seed=0,scene=None,
                          checkpoint_interval=DEFAULT_CHECKPOINT):
    """Execute a real long game and return a fully reconstructible ledger."""
    if type(seed) is not int or not 0<=seed<=2**31-1:
        raise RoguelikeLongrunError("original campaign seed out of bounds")
    if (type(checkpoint_interval) is not int or not
        8<=checkpoint_interval<=128):
        raise RoguelikeLongrunError("checkpoint interval must be between 8 and 128")
    _bound_actions(actions)
    config=make_editor_document("roguelike",settings)
    rules=config["settings"]
    source=None
    if scene is not None:
        source=validate_advanced_scene(scene,rules)
        if source["editor"]!="roguelike" or source["seed"]!=seed:
            raise RoguelikeLongrunError("authored starting floor identity must match seed")
    state=start(rules,seed)
    if source is not None:
        apply_scene(state,rules,source["layout"])
    origin={
        "schema":SCHEMA,"editor":"roguelike",
        "settings_digest":config["digest"],"seed":seed,
        "scene_digest":source["digest"] if source is not None else None,
        "checkpoint_interval":checkpoint_interval,
        "authority":"independent_original_gameplay_reexecution",
    }
    genesis=_digest(origin)
    head=genesis;chunks=[]
    turn_events=[]
    for index,action in enumerate(actions):
        if state["failed"] or state["finished"]:
            raise RoguelikeLongrunError("terminal campaign cannot accept additional actions")
        try:
            events=step(state,rules,action)
        except RoguelikeActionError as exc:
            raise RoguelikeLongrunError(
                "illegal real dungeon action at "+str(index)+": "+str(exc)) from exc
        turn_events.append({
            "index":index,"action":action,
            "events_digest":_digest(events),
            "state_digest":_digest(state),
        })
        if len(turn_events)==checkpoint_interval or index==len(actions)-1:
            chunk={
                "index":len(chunks),"start_turn":turn_events[0]["index"],
                "turn_count":len(turn_events),"prior_digest":head,
                "action_window_digest":_digest([x["action"] for x in turn_events]),
                "events_and_states_digest":_digest(turn_events),
                "final_floor":state["floor"],
                "state_digest":_digest(state),
                "terminal":state["failed"] or state["finished"],
            }
            chunk["digest"]=_digest(chunk)
            head=chunk["digest"]
            chunks.append(chunk)
            turn_events=[]
    result={
        **origin,
        "genesis_digest":genesis,
        "actions":list(actions),
        "turn_count":len(actions),
        "checkpoints":chunks,
        "checkpoint_count":len(chunks),
        "head_digest":head,
        "state":state,
        "terminal":state["failed"] or state["finished"],
        "victory":state["victory"],
        "native_engine_certified":False,
        "hardware_execution_verified":False,
        "commercial_publication_certified":False,
        "unverified_checkpoint_state_accepted":False,
    }
    return {**result,"digest":_digest(result)}


def verify_long_roguelike(record,settings=None):
    """Fail closed by replaying every action rather than trusting snapshots."""
    if type(record) is not dict or record.get("schema")!=SCHEMA:
        raise RoguelikeLongrunError("exact original longrun schema is required")
    reconstructed=replay_long_roguelike(
        settings,record.get("actions"),seed=record.get("seed"),
        scene=record.get("scene"),
        checkpoint_interval=record.get("checkpoint_interval"))
    if record!=reconstructed:
        raise RoguelikeLongrunError("record, prior checkpoint chain or actual game state has been forged")
    return True


def continue_long_roguelike(previous,more_actions,settings=None):
    """Verified restart + append. Never load the serialized state as authority.

    Source custody demands the same concrete scene/settings on continuation.
    Replay from genesis is deliberate fail-closed behavior; optimizations
    require independently verified checkpoint promotion.
    """
    if type(previous) is not dict:
        raise RoguelikeLongrunError("a verified prior longrun record is required")
    verify_long_roguelike(previous,settings)
    _bound_actions(more_actions)
    if previous["terminal"] and more_actions:
        raise RoguelikeLongrunError("cannot continue a defeated or completed dungeon")
    commands=previous["actions"]+list(more_actions)
    _bound_actions(commands)
    return replay_long_roguelike(
        settings,commands,seed=previous["seed"],scene=previous.get("scene"),
        checkpoint_interval=previous["checkpoint_interval"])


__all__=["SCHEMA","MAX_COMMANDS","RoguelikeLongrunError",
         "replay_long_roguelike","verify_long_roguelike",
         "continue_long_roguelike"]
