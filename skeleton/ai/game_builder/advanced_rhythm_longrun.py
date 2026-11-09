"""Verified full-length original rhythm chart runner with zero trusted snapshots.

Never changes the shared 128-action session gate. Long sessions are segmented
into replay-verifiable windows, every note judgement and input-driven clock
reconstructed from the original author-reviewed source on continuation.
"""
from __future__ import annotations
from hashlib import sha256
import json

from .advanced_rhythm_runtime import (ACTIONS,RhythmActionError,
                                      start,step,apply_scene)
from .advanced_level_scenes import validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.rhythm_long_chart.v1"
MAX_ACTIONS=4096
MAX_CHECKPOINTS=256
DEFAULT_CHECKPOINT=64


class RhythmLongChartError(ValueError):
    """Unsupported signed source, forged chronology or untrusted continuation."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                 ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _actions(value):
    if type(value) not in (tuple,list) or len(value)>MAX_ACTIONS or any(
        type(command) is not str or command not in ACTIONS for command in value):
        raise RhythmLongChartError("rhythm commands must be bounded and registered")
    return list(value)


def run_long_rhythm(settings=None,actions=(),*,seed=0,scene=None,
                    checkpoint_interval=DEFAULT_CHECKPOINT):
    if type(seed) is not int or not 0<=seed<=2**31-1:
        raise RhythmLongChartError("rhythm seed must be exact bounded integer")
    if type(checkpoint_interval) is not int or not (
        16<=checkpoint_interval<=128):
        raise RhythmLongChartError("rhythm checkpoint interval must be 16..128")
    commands=_actions(actions)
    config=make_editor_document("rhythm",settings)
    rules=config["settings"]
    source=None
    if scene is not None:
        source=validate_advanced_scene(scene,rules)
        if source["editor"]!="rhythm" or source["seed"]!=seed:
            raise RhythmLongChartError("original authored rhythm source identity changed")
    state=start(rules,seed)
    if source is not None:
        apply_scene(state,rules,source["layout"])
    custody={
        "schema":SCHEMA,"editor":"rhythm","seed":seed,
        "settings_digest":config["digest"],
        "scene_digest":source["digest"] if source else None,
        "checkpoint_interval":checkpoint_interval,
        "authority":"full_source_clock_and_note_reexecution",
    }
    genesis=_digest(custody);head=genesis;checkpoints=[];window=[]
    for index,action in enumerate(commands):
        if state["finished"] or state["failed"]:
            raise RhythmLongChartError("terminal original song cannot be extended")
        try:events=step(state,rules,action)
        except RhythmActionError as exc:
            raise RhythmLongChartError(
                "unreplayable authentic rhythm action "+str(index)+": "+str(exc)
            ) from exc
        window.append({
            "turn":index,"action":action,"events_digest":_digest(events),
            "judgement_digest":_digest(state["judgements"]),
            "state_digest":_digest(state),
        })
        if len(window)==checkpoint_interval or index==len(commands)-1:
            checkpoint={
                "index":len(checkpoints),
                "first_turn":window[0]["turn"],
                "turn_count":len(window),
                "previous_digest":head,
                "action_window_digest":_digest([row["action"] for row in window]),
                "verified_transition_digest":_digest(window),
                "clock_ms":state["clock_ms"],
                "state_digest":_digest(state),
                "terminal":state["finished"] or state["failed"],
            }
            checkpoint["digest"]=_digest(checkpoint)
            checkpoints.append(checkpoint)
            head=checkpoint["digest"]
            window=[]
    record={
        **custody,"source":source,"genesis_digest":genesis,
        "actions":commands,"turn_count":len(commands),
        "checkpoints":checkpoints,"checkpoint_count":len(checkpoints),
        "head_digest":head,"state":state,
        "finished":state["finished"],"failed":state["failed"],
        "victory":state["victory"],"accuracy":state["accuracy"],
        "audio_certified":False,"native_execution_certified":False,
        "untrusted_state_promoted":False,
    }
    return {**record,"digest":_digest(record)}


def verify_long_rhythm(record,settings=None):
    if type(record) is not dict or record.get("schema")!=SCHEMA:
        raise RhythmLongChartError("exact original long-chart evidence required")
    replay=run_long_rhythm(
        settings,record.get("actions"),seed=record.get("seed"),
        scene=record.get("source"),
        checkpoint_interval=record.get("checkpoint_interval"),
    )
    if replay!=record:
        raise RhythmLongChartError("long-chart history, score, state or source receipt is forged")
    return True


def continue_long_rhythm(record,next_actions,settings=None):
    if type(record) is not dict:
        raise RhythmLongChartError("full verified original song record required")
    verify_long_rhythm(record,settings)
    additional=_actions(next_actions)
    if (record["finished"] or record["failed"]) and additional:
        raise RhythmLongChartError("cannot extend an authenticated terminal chart")
    combined=_actions(record["actions"]+additional)
    return run_long_rhythm(
        settings,combined,seed=record["seed"],scene=record["source"],
        checkpoint_interval=record["checkpoint_interval"]
    )


__all__=["SCHEMA","MAX_ACTIONS","RhythmLongChartError",
         "run_long_rhythm","verify_long_rhythm","continue_long_rhythm"]
