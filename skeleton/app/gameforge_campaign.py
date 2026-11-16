"""Connect authored NPC conversations to generated GameForge quest play.

No additional quest or dialogue engine is defined here. The authoritative
owners validate their own event streams. Dialogue grants unlock objectives
only in the independently supplied, source-bound campaign contract.
"""
from __future__ import annotations

import json
from typing import Any

from skeleton.app.gameforge_quest_bridge import (
    MAX_ACTIONS, _route, _session, _steps, build_design,
)
from skeleton.app.original_quest_cli import (
    _encode, _object, _require, _strings, _text,
)
from skeleton.game.gameplay.dialogue_graph import (
    replay as dialogue_replay, validate_source as validate_dialogue,
)
from skeleton.gameforge.errors import GameForgeError
from skeleton.gameforge.safety import screen_text
import hashlib

REQUEST_SCHEMA = "skeleton.gameforge.campaign.request.v1"
DESIGN_SCHEMA = "skeleton.gameforge.campaign.design.v1"
SESSION_SCHEMA = "skeleton.gameforge.campaign.session.v1"
MAX_CONVERSATIONS = 16
MAX_CHOICES = 128
MAX_CAMPAIGN_ACTIONS = MAX_ACTIONS


def digest(value: Any) -> str:
    return hashlib.sha256(_encode(value)).hexdigest()


def detached(value: Any) -> Any:
    return json.loads(_encode(value))


def _admit(source: Any) -> tuple[dict, dict, dict]:
    data = _object(detached(source), {"schema", "quest_request", "dialogues"})
    _require(data["schema"] == REQUEST_SCHEMA, "unsupported campaign schema")
    base = build_design(data["quest_request"])
    world = base["world"]
    objectives = {row["id"] for row in _steps(base["quest_receipt"]["artifact"])}
    raw = data["dialogues"]
    _require(type(raw) is list and 1 <= len(raw) <= MAX_CONVERSATIONS,
             "invalid conversation count")
    conversations, gates = {}, {}
    for entry in raw:
        row = _object(entry, {"npc", "source", "gates", "witness"})
        npc = _text(row["npc"], 128)
        _require(npc in world["npcs"] and npc not in conversations,
                 "missing or duplicate conversation NPC")
        authored = validate_dialogue(row["source"])
        _require(authored["world_id"] == base["conductor_manifest"]["game_id"],
                 "conversation belongs to another world")
        _require(authored["conversation_id"] not in
                 {c["source"]["conversation_id"] for c in conversations.values()},
                 "duplicate conversation identity")
        screen_text("dialogue", *(node["text"] for node in authored["nodes"]))
        bindings = row["gates"]
        _require(type(bindings) is dict and 1 <= len(bindings) <= 128,
                 "invalid objective gate map")
        witness = row["witness"]
        _require(type(witness) is list and 1 <= len(witness) <= MAX_CHOICES,
                 "invalid conversation witness")
        for choice in witness:
            _text(choice, 128)
        ended = dialogue_replay(authored, witness)
        _require(ended["state"]["phase"] == "ended", "witness must reach an authored ending")
        grants = set(ended["state"]["quests"])
        for objective, grant in bindings.items():
            _text(objective, 128)
            _text(grant, 128)
            _require(objective in objectives and objective not in gates and grant in grants,
                     "missing, duplicate or unearned dialogue gate")
            gates[objective] = (npc, grant)
        conversations[npc] = {"source": authored, "witness": witness}
    return base, conversations, gates


def _gate_open(gate: tuple[str, str], dialogue: dict) -> bool:
    npc, grant = gate
    saved = dialogue[npc]
    return saved["state"]["phase"] == "ended" and grant in saved["state"]["quests"]


def _replay(source: Any, base: dict, conversations: dict, gates: dict, actions: Any) -> dict:
    actions = detached(actions)
    _require(type(actions) is list and len(actions) <= MAX_CAMPAIGN_ACTIONS,
             "campaign action count invalid")
    world = base["world"]
    location = world["start"]
    dialogue = {npc: dialogue_replay(row["source"], [])
                for npc, row in conversations.items()}
    projected: list[dict] = []
    resolved: set[str] = set()
    number_of_objectives = len(_steps(base["quest_receipt"]["artifact"]))
    for raw in actions:
        _require(len(resolved) < number_of_objectives, "campaign already completed")
        _require(type(raw) is dict, "campaign action must be an object")
        kind = raw.get("type")
        if kind == "dialogue":
            action = _object(raw, {"type", "npc", "choice"})
            npc = _text(action["npc"], 128)
            choice = _text(action["choice"], 128)
            _require(npc in conversations and world["npcs"][npc] == location,
                     "conversation unavailable at current location")
            old = dialogue[npc]
            _require(old["state"]["phase"] == "active", "conversation is terminal")
            dialogue[npc] = dialogue_replay(conversations[npc]["source"],
                                            [*old["choices"], choice])
        elif kind == "move":
            action = _object(raw, {"type", "to"})
            destination = _text(action["to"], 64)
            _require(destination in world["edges"][location], "illegal region travel")
            location = destination
            projected.append(action)
        elif kind == "resolve":
            action = _object(raw, {"type", "objective", "npc"})
            objective = _text(action["objective"], 128)
            _require(objective not in resolved, "objective already resolved")
            if objective in gates:
                _require(_gate_open(gates[objective], dialogue), "objective dialogue grant missing")
            resolved.add(objective)
            projected.append(action)
        else:
            raise ValueError("unsupported campaign event")
    # Canonical quest replay validates objective order, exact NPC and rewards.
    quest = _session(source["quest_request"], base, projected)
    state = quest["state"]
    _require(state["location"] == location and state["resolutions"] == len(resolved),
             "campaign and canonical quest state diverged")
    legal = []
    locked = []
    if state["status"] == "in_progress":
        for action in state["legal_actions"]:
            if action["type"] == "resolve" and action["objective"] in gates:
                npc, grant = gates[action["objective"]]
                if not _gate_open((npc, grant), dialogue):
                    locked.append({"objective": action["objective"], "npc": npc,
                                   "required_grant": grant})
                    continue
            legal.append(action)
        for npc, row in sorted(conversations.items()):
            saved = dialogue[npc]
            if world["npcs"][npc] != location or saved["state"]["phase"] != "active":
                continue
            node = next(node for node in row["source"]["nodes"]
                        if node["id"] == saved["state"]["node_id"])
            flags = set(saved["state"]["flags"])
            for choice in node["choices"]:
                if set(choice["requires"]) <= flags:
                    # The owner remains the final authority for every offered action.
                    dialogue_replay(row["source"], [*saved["choices"], choice["id"]])
                    legal.append({"type": "dialogue", "npc": npc, "choice": choice["id"]})
    return {"quest": quest, "dialogues": dialogue, "location": location,
            "status": state["status"], "earned_rewards": state["earned_rewards"],
            "legal_actions": legal, "locked_objectives_here": locked}


def _witness(base: dict, conversations: dict, gates: dict) -> list[dict]:
    world = base["world"]
    location = world["start"]
    actions: list[dict] = []
    completed_dialogues: set[str] = set()

    def move(target: str) -> None:
        nonlocal location
        actions.extend({"type": "move", "to": dest}
                       for dest in _route(world["edges"], location, target)[1:])
        location = target

    for step in _steps(base["quest_receipt"]["artifact"]):
        if step["id"] in gates:
            npc, _ = gates[step["id"]]
            if npc not in completed_dialogues:
                move(world["npcs"][npc])
                actions.extend({"type": "dialogue", "npc": npc, "choice": choice}
                               for choice in conversations[npc]["witness"])
                completed_dialogues.add(npc)
        move(step["location"])
        actions.append({"type": "resolve", "objective": step["id"], "npc": step["npc"]})
    _require(len(actions) <= MAX_CAMPAIGN_ACTIONS, "campaign witness exceeds budget")
    return actions


def _design(source: Any, base: dict, conversations: dict, gates: dict) -> dict:
    actions = _witness(base, conversations, gates)
    result = _replay(source, base, conversations, gates, actions)
    _require(result["status"] == "completed" and
             result["earned_rewards"] == base["route_replay"]["earned_rewards"],
             "campaign witness does not complete the canonical quest")
    body = {"schema": DESIGN_SCHEMA, "source_digest": digest(source),
            "base_design_digest": base["design_digest"], "world": base["world"],
            "gate_bindings": {oid: {"npc": npc, "grant": grant}
                              for oid, (npc, grant) in sorted(gates.items())},
            "witness": actions, "witness_state": result,
            "native_qualified": False, "release_qualified": False}
    receipt = {**body, "design_digest": digest(body)}
    _encode({"request": source, "receipt": receipt})
    return receipt


def build_campaign(source: Any) -> dict:
    return _design(source, *_admit(source))


def play_campaign(source: Any, actions: Any) -> dict:
    base, conversations, gates = _admit(source)
    design = _design(source, base, conversations, gates)
    state = _replay(source, base, conversations, gates, actions)
    body = {"schema": SESSION_SCHEMA, "source_digest": design["source_digest"],
            "design_digest": design["design_digest"], "actions": detached(actions),
            "state": state, "native_qualified": False, "release_qualified": False}
    receipt = {**body, "session_digest": digest(body)}
    _encode({"request": source, "receipt": receipt})
    return detached(receipt)


def verify_campaign(source: Any, receipt: Any) -> bool:
    try:
        return _encode(receipt) == _encode(build_campaign(source))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def verify_session(source: Any, receipt: Any) -> bool:
    try:
        return _encode(receipt) == _encode(play_campaign(source, receipt["actions"]))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def append_actions(source: Any, previous: Any, additional: Any) -> dict:
    _encode({"request": source, "receipt": previous, "additional": additional})
    _require(verify_session(source, previous), "campaign checkpoint mismatch")
    _require(type(additional) is list and 1 <= len(additional) <= MAX_CAMPAIGN_ACTIONS,
             "invalid campaign append")
    return play_campaign(source, previous["actions"] + additional)
