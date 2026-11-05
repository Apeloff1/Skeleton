"""Bounded, replay-proven path and interaction solver for playable grid games.

Search uses actual movement, collision, combat, inventory, crafting and
quest/ending transitions from the canonical offline grid campaign.
A budget-limited search is inconclusive, never proof of impossibility.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from .flgb_gameplay_runtime import GameplayContractError, dig, req_id
from .offline_grid_campaign import (
    Campaign, Command, DIRECTIONS, Session,
)

SCHEMA = "skeleton.grid_playthrough_route.v1"
MAX_NODES = 4096
MAX_DEPTH = 128
MAX_TRANSITIONS = 32768


def _key(session: Session) -> tuple[Any, ...]:
    """Future legal actions depend on state, not journal display order."""
    return (
        session.x, session.y, session.inventory, session.spoken,
        session.quests, session.ending, session.health, session.enemies,
    )


def _options(session: Session) -> list[tuple[str, str]]:
    source = session.campaign.spec
    options: list[tuple[str, str]] = []
    for obj in source["objects"]:
        if (obj["x"], obj["y"]) == (session.x, session.y):
            if obj["kind"] == "item" and obj["id"] not in session.inventory:
                options.append(("collect", obj["id"]))
            elif obj["kind"] == "npc" and obj["id"] not in session.spoken:
                options.append(("talk", obj["id"]))
        if (obj["kind"] == "enemy"
                and dict(session.enemies).get(obj["id"], 0) > 0
                and abs(obj["x"] - session.x) + abs(obj["y"] - session.y) == 1):
            options.append(("strike", obj["id"]))
    for recipe in source.get("recipes", []):
        if (set(recipe["ingredients"]) <= set(session.inventory)
                and recipe["product"] not in session.inventory):
            options.append(("craft", recipe["id"]))
    for direction in sorted(DIRECTIONS):
        options.append(("move", direction))
    if source["rows"][session.y][session.x] == "G":
        for ending in source["endings"]:
            if set(ending["requires_quests"]) <= set(session.quests):
                options.append(("finish", ending["id"]))
    return sorted(options)


def _report(
    campaign: Campaign, goal: str, status: str, expanded: int,
    visited: int, transitions: int, witness: Session | None,
    max_nodes: int, max_depth: int,
) -> dict[str, Any]:
    report = {
        "schema_version": SCHEMA,
        "source_digest": campaign.source_digest,
        "goal_ending": goal,
        "max_nodes": max_nodes,
        "max_depth": max_depth,
        "status": status,
        "expanded": expanded,
        "visited": visited,
        "transitions": transitions,
        "commands": [
            {"command_id": e["command_id"], "kind": e["kind"],
             "target": e["target"]}
            for e in witness.events
        ] if witness is not None else [],
        "state_digest": witness.state_digest if witness is not None else None,
        "save": witness.snapshot() if witness is not None else None,
    }
    report["checksum"] = dig(report)
    return report


def plan_playthrough(
    campaign: Campaign, goal_ending: str, *, max_nodes: int = 1024,
    max_depth: int = 64,
) -> dict[str, Any]:
    """Shortest legal command sequence to the selected authored ending."""
    if not isinstance(campaign, Campaign):
        raise GameplayContractError("invalid canonical grid campaign")
    req_id(goal_ending, "goal ending")
    if goal_ending not in {e["id"] for e in campaign.spec["endings"]}:
        raise GameplayContractError("unknown authored grid ending")
    if type(max_nodes) is not int or not 1 <= max_nodes <= MAX_NODES:
        raise GameplayContractError("invalid grid search node budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise GameplayContractError("invalid grid search depth budget")
    start = Session.new(campaign)
    queue = deque([start])
    seen = {_key(start)}
    expanded = 0
    transitions = 0
    incomplete = False
    while queue:
        if expanded >= max_nodes:
            incomplete = True
            break
        session = queue.popleft()
        expanded += 1
        if session.ending == goal_ending:
            restored = Session.restore(campaign, session.snapshot())
            if restored.state_digest != session.state_digest:
                raise GameplayContractError("grid route replay mismatch")
            return _report(campaign, goal_ending, "solved", expanded,
                           len(seen), transitions, restored, max_nodes, max_depth)
        if session.ending is not None:
            continue
        if session.tick >= max_depth:
            incomplete = True
            continue
        for kind, target in _options(session):
            if transitions >= MAX_TRANSITIONS:
                incomplete = True
                queue.clear()
                break
            # Count even rejected collisions/combat; no invalid-path CPU escape.
            transitions += 1
            action = Command(f"route-{session.tick + 1}", kind, target)
            try:
                candidate = session.step(action)
            except GameplayContractError:
                continue
            if candidate.ending == goal_ending:
                restored = Session.restore(campaign, candidate.snapshot())
                if restored.state_digest != candidate.state_digest:
                    raise GameplayContractError("grid route replay mismatch")
                return _report(campaign, goal_ending, "solved", expanded,
                               len(seen) + 1, transitions, restored,
                               max_nodes, max_depth)
            if candidate.ending is not None:
                continue
            key = _key(candidate)
            if key not in seen:
                if len(seen) >= max_nodes:
                    incomplete = True
                    queue.clear()
                    break
                seen.add(key)
                queue.append(candidate)
            if incomplete and not queue:
                break
    return _report(
        campaign, goal_ending,
        "inconclusive" if incomplete else "unreachable",
        expanded, len(seen), transitions, None, max_nodes, max_depth,
    )


def verify_playthrough(
    campaign: Campaign, payload: Any,
) -> dict[str, Any]:
    """Recompute search and replay source-bound command receipts."""
    keys = {
        "schema_version", "source_digest", "goal_ending", "max_nodes",
        "max_depth", "status", "expanded", "visited", "transitions",
        "commands", "state_digest", "save", "checksum",
    }
    if type(payload) is not dict or set(payload) != keys:
        raise GameplayContractError("invalid grid route report fields")
    if payload["schema_version"] != SCHEMA:
        raise GameplayContractError("unsupported grid route schema")
    if payload["source_digest"] != campaign.source_digest:
        raise GameplayContractError("grid route source mismatch")
    expected = plan_playthrough(
        campaign, payload["goal_ending"],
        max_nodes=payload["max_nodes"], max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise GameplayContractError("grid route replay or checksum mismatch")
    if expected["status"] == "solved":
        session = Session.restore(campaign, expected["save"])
        if session.ending != expected["goal_ending"]:
            raise GameplayContractError("grid route ending mismatch")
    return expected
