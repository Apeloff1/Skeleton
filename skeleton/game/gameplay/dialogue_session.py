"""Source-bound authored dialogue replay with canonical FLGB events and saves."""
from __future__ import annotations
from copy import deepcopy
import json
from typing import Any, Mapping, Sequence
from skeleton.game.gameplay.flgb_gameplay_runtime import (
    DialogueChoice, DialogueNode, EventBus, SaveableGameplayState, dig,
    req_id, validate_dialogue,
)
SCHEMA = "skeleton.game.dialogue_session.v1"
SAVE_SCHEMA = "skeleton.game.dialogue_save.v1"
MAX_STEPS = 128

class DialogueSessionError(ValueError):
    """Invalid source, choice or replay."""

def _id(value: Any) -> str:
    try:
        return req_id(value, "dialogue id")
    except ValueError as exc:
        raise DialogueSessionError("invalid dialogue id") from exc

def _digest(value: Any) -> str:
    return dig(value)

def _check_object(value: Any, allowed: set[str], required: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) - allowed or not required <= set(value):
        raise DialogueSessionError("invalid dialogue fields")
    return value

def validate_source(value: Any) -> dict:
    source = _check_object(value, {"schema", "world_id", "conversation_id",
        "start_node", "ending_ids", "nodes"}, {"schema", "world_id",
        "conversation_id", "start_node", "ending_ids", "nodes"})
    if source["schema"] != SCHEMA:
        raise DialogueSessionError("unsupported source version")
    for key in ("world_id", "conversation_id", "start_node"):
        _id(source[key])
    ends = source["ending_ids"]
    nodes = source["nodes"]
    if type(ends) is not list or not 1 <= len(ends) <= 64:
        raise DialogueSessionError("invalid ending IDs")
    if type(nodes) is not list or not 1 <= len(nodes) <= 64:
        raise DialogueSessionError("invalid dialogue node count")
    for ending in ends:
        _id(ending)
    if len(set(ends)) != len(ends):
        raise DialogueSessionError("duplicate ending IDs")
    typed = []
    names = []
    for raw in nodes:
        node = _check_object(raw, {"id", "text", "choices"}, {"id", "text", "choices"})
        name = _id(node["id"])
        names.append(name)
        if not isinstance(node["text"], str) or not 1 <= len(node["text"]) <= 500:
            raise DialogueSessionError("invalid dialogue text")
        if type(node["choices"]) is not list or len(node["choices"]) > 8:
            raise DialogueSessionError("invalid dialogue choice count")
        choices = []
        for raw_choice in node["choices"]:
            choice = _check_object(raw_choice,
                {"id", "target", "requires", "grants", "reputation_delta", "quest_id"},
                {"id", "target", "requires", "grants", "reputation_delta"})
            for field in ("requires", "grants"):
                flags = choice[field]
                if type(flags) is not list or len(flags) > 64:
                    raise DialogueSessionError("invalid dialogue flags")
                for flag in flags:
                    _id(flag)
                if len(set(flags)) != len(flags):
                    raise DialogueSessionError("duplicate dialogue flags")
            delta = choice["reputation_delta"]
            if type(delta) is not int or not -20 <= delta <= 20:
                raise DialogueSessionError("invalid reputation delta")
            if "quest_id" in choice:
                _id(choice["quest_id"])
            choices.append(DialogueChoice(_id(choice["id"]), _id(choice["target"]),
                                          _digest(choice["requires"])))
        typed.append(DialogueNode(name, _digest(node["text"]), tuple(choices)))
    if len(set(names)) != len(names) or source["start_node"] not in names or not set(ends) <= set(names):
        raise DialogueSessionError("missing or duplicate dialogue nodes")
    try:
        validate_dialogue(typed)
    except ValueError as exc:
        raise DialogueSessionError("invalid dialogue edges") from exc
    for node in nodes:
        if bool(node["choices"]) == (node["id"] in ends):
            raise DialogueSessionError("ending nodes must be terminal")
    try:
        frozen = json.loads(json.dumps(source, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError, RecursionError) as exc:
        raise DialogueSessionError("noncanonical dialogue source") from exc
    if len(json.dumps(frozen, sort_keys=True)) > 65536:
        raise DialogueSessionError("dialogue source too large")
    return frozen

def replay(source: Mapping[str, Any], choices: Sequence[str]) -> dict:
    authored = validate_source(dict(source))
    if type(choices) not in (tuple, list) or len(choices) > MAX_STEPS:
        raise DialogueSessionError("dialogue step limit")
    state = {"node_id": authored["start_node"], "step": 0,
             "flags": [], "reputation": 0, "quests": [], "phase": "active"}
    nodes = {node["id"]: node for node in authored["nodes"]}
    if state["node_id"] in authored["ending_ids"]:
        state["phase"] = "ended"
    bus = EventBus()
    trace = []
    for selected in choices:
        if state["phase"] != "active":
            raise DialogueSessionError("dialogue already ended")
        _id(selected)
        found = [c for c in nodes[state["node_id"]]["choices"] if c["id"] == selected]
        if len(found) != 1:
            raise DialogueSessionError("choice not offered")
        choice = found[0]
        if not set(choice["requires"]) <= set(state["flags"]):
            raise DialogueSessionError("choice prerequisite missing")
        flags = set(state["flags"]) | set(choice["grants"])
        if len(flags) > 64:
            raise DialogueSessionError("flag budget exceeded")
        state["flags"] = sorted(flags)
        state["reputation"] = max(-100, min(100, state["reputation"] + choice["reputation_delta"]))
        if "quest_id" in choice:
            quests = set(state["quests"]) | {choice["quest_id"]}
            if len(quests) > 64:
                raise DialogueSessionError("quest budget exceeded")
            state["quests"] = sorted(quests)
        state["node_id"] = choice["target"]
        state["step"] += 1
        if state["node_id"] in authored["ending_ids"]:
            state["phase"] = "ended"
        event = {"choice_id": selected, "step": state["step"],
                 "node_id": state["node_id"], "flags": state["flags"],
                 "reputation": state["reputation"], "quests": state["quests"]}
        trace.append(deepcopy(event))
        bus = bus.publish("dialogue.choice", authored["conversation_id"], _digest(event))
    if state["phase"] == "active" and len(choices) == MAX_STEPS:
        state["phase"] = "step_limit"
    source_digest = _digest(authored)
    canon_digest = _digest({"world_id": authored["world_id"],
                            "conversation_id": authored["conversation_id"],
                            "source_digest": source_digest})
    save = SaveableGameplayState(world_id=authored["world_id"], schema_version=1,
                                tick=state["step"], state_digest=_digest(state),
                                canon_digest=canon_digest)
    return {"schema": SAVE_SCHEMA, "source_digest": source_digest,
            "choices": deepcopy(list(choices)), "state": state, "trace": trace,
            "state_digest": _digest(state), "event_digest": bus.digest,
            "save_metadata_digest": save.digest, "terminal": state["phase"] != "active"}

def verify_save(source: Mapping[str, Any], save: Any) -> dict:
    fields = {"schema", "source_digest", "choices", "state", "trace",
              "state_digest", "event_digest", "save_metadata_digest", "terminal"}
    _check_object(save, fields, fields)
    if save["schema"] != SAVE_SCHEMA:
        raise DialogueSessionError("unsupported save version")
    expected = replay(source, save["choices"])
    if json.dumps(save, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise DialogueSessionError("dialogue replay mismatch")
    return expected

def choose(source: Mapping[str, Any], save: Any, choice_id: str) -> dict:
    prior = replay(source, []) if save is None else verify_save(source, save)
    if prior["terminal"]:
        raise DialogueSessionError("dialogue terminal")
    return replay(source, [*prior["choices"], _id(choice_id)])
