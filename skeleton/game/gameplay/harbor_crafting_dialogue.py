"""Playable merchant dialogue with earned quest flags and delivery gates.

Dialogue actions consume canonical world ticks (as waits), so NPC patrols,
collisions and the underlying crafting campaign remain authoritative. The
overlay records original choices and replays them into deterministic trust,
flags and legal delivery consequences.
"""
from __future__ import annotations

from copy import deepcopy
from collections import deque
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, export_bundle, initial_state, normalize_action,
    step, validate_source, verify_bundle,
)

BOARD_SCHEMA = "skeleton.game.harbor.dialogue-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.dialogue-report.v1"
MAX_BOARD_BYTES = 16384
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 3
MAX_NODES = 12
MAX_CHOICES = 4
BOARD_FIELDS = {"schema", "source_id", "speaker", "required_flag_for_delivery", "nodes"}
REPORT_FIELDS = {
    "schema", "source", "board", "source_digest", "board_digest",
    "input_actions", "bundle", "events", "trust", "flags",
    "spoken_nodes", "report_digest",
}


def validate_dialogue_board(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, BOARD_FIELDS, "dialogue board")
    if (board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]
            or board["speaker"] != world["npc"]["id"]):
        raise HarborError("dialogue source or speaker mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("dialogue board exceeds byte limit")
    required = _identifier(board["required_flag_for_delivery"], "delivery permit")
    nodes = board["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise HarborError("invalid dialogue nodes")
    ids: set[str] = set()
    granted: set[str] = set()
    for node in nodes:
        _keys(node, {"id", "requires", "min_trust", "choices"}, "dialogue node")
        name = _identifier(node["id"], "dialogue node id")
        if name in ids:
            raise HarborError("duplicate dialogue node")
        ids.add(name)
        requires = node["requires"]
        if (not isinstance(requires, list) or len(requires) > 8
                or any(type(flag) is not str for flag in requires)
                or len(set(requires)) != len(requires)):
            raise HarborError("invalid dialogue prerequisites")
        for flag in requires:
            _identifier(flag, "dialogue prerequisite")
        _integer(node["min_trust"], -20, 20, "dialogue minimum trust")
        choices = node["choices"]
        if not isinstance(choices, list) or not 1 <= len(choices) <= MAX_CHOICES:
            raise HarborError("invalid dialogue choices")
        choice_ids: set[str] = set()
        for choice in choices:
            _keys(choice, {"id", "trust_delta", "grant_flag"}, "dialogue choice")
            choice_id = _identifier(choice["id"], "dialogue choice id")
            if choice_id in choice_ids:
                raise HarborError("duplicate dialogue choice")
            choice_ids.add(choice_id)
            _integer(choice["trust_delta"], -5, 5, "dialogue trust delta")
            granted.add(_identifier(choice["grant_flag"], "dialogue grant flag"))
    if required not in granted:
        raise HarborError("dialogue delivery permit cannot be earned")
    if any(flag not in granted for node in nodes for flag in node["requires"]):
        raise HarborError("unobtainable dialogue prerequisite")
    # Prove a legal finite choice sequence can actually earn the dock permit.
    # Flag-name membership alone would accept circular prerequisites.
    queue = deque([(0, 0, frozenset())])
    visited = {(0, 0, frozenset())}
    reachable = False
    while queue:
        mask, trust, flags = queue.popleft()
        if required in flags:
            reachable = True
            break
        for index, node in enumerate(nodes):
            if mask & (1 << index) or trust < node["min_trust"]:
                continue
            if any(flag not in flags for flag in node["requires"]):
                continue
            for choice in node["choices"]:
                next_trust = trust + choice["trust_delta"]
                if not -20 <= next_trust <= 20:
                    continue
                next_flags = flags | {choice["grant_flag"]}
                state = (mask | (1 << index), next_trust, frozenset(next_flags))
                if state not in visited:
                    if len(visited) >= 4096:
                        raise HarborError("dialogue reachability budget exceeded")
                    visited.add(state)
                    queue.append(state)
    if not reachable:
        raise HarborError("dialogue delivery permit is unreachable")
    return deepcopy(board)


def _normalize(value: Any) -> dict[str, str]:
    if isinstance(value, dict) and value.get("op") == "talk":
        _keys(value, {"op", "node", "choice"}, "dialogue action")
        return {"op": "talk", "node": _identifier(value["node"], "dialogue node"),
                "choice": _identifier(value["choice"], "dialogue choice")}
    return normalize_action(value)


def _simulate(world: dict[str, Any], board: dict[str, Any],
              actions: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, str]], int, list[str], list[str]]:
    state = initial_state(world)
    trust = 0
    flags: set[str] = set()
    spoken: set[str] = set()
    events: list[dict[str, Any]] = []
    canonical_actions: list[dict[str, str]] = []
    previous = digest({"world": digest(world), "dialogue": digest(board), "genesis": True})
    for action in actions:
        before_trust = trust
        before_flags = sorted(flags)
        if action["op"] == "talk":
            if (abs(state["pos"][0] - state["npc_pos"][0])
                    + abs(state["pos"][1] - state["npc_pos"][1]) != 1):
                raise HarborError("merchant dialogue out of reach")
            node = next((n for n in board["nodes"] if n["id"] == action["node"]), None)
            if node is None:
                raise HarborError("unknown dialogue node")
            if node["id"] in spoken:
                raise HarborError("dialogue node already spoken")
            if trust < node["min_trust"] or any(flag not in flags for flag in node["requires"]):
                raise HarborError("dialogue prerequisite not earned")
            choice = next((c for c in node["choices"] if c["id"] == action["choice"]), None)
            if choice is None:
                raise HarborError("unknown dialogue choice")
            trust += choice["trust_delta"]
            if not -20 <= trust <= 20:
                raise HarborError("dialogue trust ceiling exceeded")
            flags.add(choice["grant_flag"])
            spoken.add(node["id"])
            canonical_action = {"op": "wait"}
        else:
            if (action["op"] == "deliver"
                    and board["required_flag_for_delivery"] not in flags):
                raise HarborError("dialogue delivery permit not earned")
            canonical_action = action
        advanced = step(world, state, canonical_action)
        canonical_actions.append(deepcopy(canonical_action))
        entry = {
            "tick": advanced["tick"], "action": deepcopy(action),
            "canonical_action": deepcopy(canonical_action),
            "trust_before": before_trust, "trust_after": trust,
            "flags_before": before_flags, "flags_after": sorted(flags),
            "position": list(advanced["pos"]),
            "npc_position": list(advanced["npc_pos"]),
            "state_digest": digest(advanced), "previous": previous,
        }
        entry["digest"] = digest(entry)
        events.append(entry)
        previous = entry["digest"]
        state = advanced
    return events, canonical_actions, trust, sorted(flags), sorted(spoken)


def build_dialogue_game(source: Any, board: Any, actions: Any,
                        *, require_win: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_dialogue_board(board, world)
    if not isinstance(actions, list) or len(actions) > world["max_ticks"]:
        raise HarborError("dialogue action budget exceeded")
    normalized = [_normalize(action) for action in actions]
    events, canonical_actions, trust, flags, spoken = _simulate(world, authored, normalized)
    bundle = export_bundle(world, canonical_actions, require_win=require_win)
    if [event["action"] for event in bundle["events"]] != canonical_actions:
        raise HarborError("dialogue canonical action projection mismatch")
    report = {
        "schema": REPORT_SCHEMA, "source": world, "board": authored,
        "source_digest": digest(world), "board_digest": digest(authored),
        "input_actions": normalized, "bundle": bundle,
        "events": events, "trust": trust, "flags": flags,
        "spoken_nodes": spoken,
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("dialogue report exceeds byte limit")
    return report


def verify_dialogue_game(report: Any, *, require_win: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "dialogue report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized dialogue report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("dialogue report digest mismatch")
    verify_bundle(report["bundle"], require_win=require_win)
    rebuilt = build_dialogue_game(report["source"], report["board"],
                                  report["input_actions"], require_win=require_win)
    if rebuilt != report:
        raise HarborError("dialogue replay mismatch")
    return {
        "trust": rebuilt["trust"], "flags": deepcopy(rebuilt["flags"]),
        "ending": rebuilt["bundle"]["state"]["ending"],
        "spoken_nodes": deepcopy(rebuilt["spoken_nodes"]),
        "report_digest": rebuilt["report_digest"],
    }


def resume_dialogue_game(report: Any, actions: Any, *,
                         expected_digest: str, require_win: bool = False) -> dict[str, Any]:
    status = verify_dialogue_game(report)
    if type(expected_digest) is not str or expected_digest != status["report_digest"]:
        raise HarborError("stale dialogue checkpoint")
    if report["bundle"]["state"]["ending"] is not None:
        raise HarborError("dialogue campaign already complete")
    if not isinstance(actions, list):
        raise HarborError("dialogue continuation must be a list")
    rebuilt = build_dialogue_game(
        report["source"], report["board"], report["input_actions"] + actions,
        require_win=require_win,
    )
    if rebuilt["events"][:len(report["events"])] != report["events"]:
        raise HarborError("dialogue continuation rewrote history")
    return rebuilt
