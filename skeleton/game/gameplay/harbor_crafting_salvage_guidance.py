"""Finite NPC-aware salvage action guidance with replay-verified legality."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    DIRECTIONS, HarborError, _integer, _keys, canonical, digest, step,
)
from .harbor_crafting_salvage import (
    MAX_REPORT_BYTES, build_salvage, verify_salvage,
)

SCHEMA = "skeleton.game.harbor.salvage-guidance.v1"
MAX_BYTES = MAX_REPORT_BYTES * 2
MAX_HORIZON = 32
MAX_NODES = 512
FIELDS = {"schema", "report", "horizon", "legal_actions", "recommended",
          "goal", "guidance_digest"}


def _candidates(report: dict[str, Any]) -> list[dict[str, str]]:
    board = report["board"]
    source = report["source"]
    actions = [{"op": "salvage", "site": s["id"]} for s in board["sites"]]
    actions += [{"op": "offload"}, {"op": "patch"}, {"op": "deliver"}, {"op": "rescue"}]
    actions += [{"op": "gather"}, {"op": "wait"}]
    actions += [{"op": "craft", "recipe": r["id"]} for r in source["recipes"]]
    actions += [{"op": "trade", "item": i} for i in sorted(source["npc"]["stock"])]
    actions += [{"op": "move", "direction": direction} for direction in DIRECTIONS]
    return actions


def _goal(report: dict[str, Any]) -> tuple[str, list[list[int]]]:
    state = report["state"]
    board = report["board"]
    source = report["source"]
    secured = set(state["secured"])
    cargo = set(state["cargo"])
    remaining = [site for site in board["sites"] if site["id"] not in secured | cargo]
    weight = sum(site["weight"] for site in board["sites"] if site["id"] in cargo)
    if cargo and (not remaining or all(
            weight + site["weight"] > board["cargo_capacity"] for site in remaining)):
        dock = source["dock"]
        return "dock-offload", [[dock[0] + dx, dock[1] + dy]
                                for dx, dy in DIRECTIONS.values()]
    if remaining:
        return "salvage:" + remaining[0]["id"], [remaining[0]["at"]]
    dock = source["dock"]
    return "dock-rescue", [[dock[0] + dx, dock[1] + dy]
                            for dx, dy in DIRECTIONS.values()]


def _route(report: dict[str, Any], goals: list[list[int]], horizon: int) -> dict[str, str] | None:
    world = report["source"]
    initial = report["bundle"]["state"]
    queue = deque([(initial, None, 0)])
    seen = set()
    while queue and len(seen) < MAX_NODES:
        state, first, depth = queue.popleft()
        key = (tuple(state["pos"]), tuple(state["npc_pos"]),
               state["tick"] % len(world["npc"]["route"]))
        if key in seen:
            continue
        seen.add(key)
        if state["pos"] in goals and first is not None:
            return first
        if depth >= horizon:
            continue
        for direction in ("north", "east", "south", "west"):
            action = {"op": "move", "direction": direction}
            try:
                next_state = step(world, state, action)
            except HarborError:
                continue
            queue.append((next_state, first or action, depth + 1))
        try:
            next_state = step(world, state, {"op": "wait"})
            queue.append((next_state, first or {"op": "wait"}, depth + 1))
        except HarborError:
            pass
    return None


def build_salvage_guidance(report: Any, *, horizon: int = 16) -> dict[str, Any]:
    verify_salvage(report)
    _integer(horizon, 1, MAX_HORIZON, "salvage guidance horizon")
    legal: list[dict[str, str]] = []
    if not report["state"]["complete"] and not report["state"]["failed"]:
        for action in _candidates(report):
            try:
                build_salvage(report["source"], report["board"], report["actions"] + [action])
            except HarborError:
                continue
            legal.append(action)
    name, goals = _goal(report)
    special = next((a for a in legal if a["op"] in {"salvage", "offload", "rescue"}
                    and (a["op"] != "salvage" or name == "salvage:" + a["site"])), None)
    recommended = special
    if recommended is None and legal:
        path_action = _route(report, goals, horizon)
        recommended = path_action if path_action in legal else legal[0]
    guidance = {"schema": SCHEMA, "report": deepcopy(report), "horizon": horizon,
                "legal_actions": legal, "recommended": recommended, "goal": name}
    guidance["guidance_digest"] = digest(guidance)
    if len(canonical(guidance)) > MAX_BYTES:
        raise HarborError("salvage guidance exceeds byte budget")
    return guidance


def verify_salvage_guidance(guidance: Any) -> dict[str, Any]:
    _keys(guidance, FIELDS, "salvage guidance")
    if guidance["schema"] != SCHEMA or len(canonical(guidance)) > MAX_BYTES:
        raise HarborError("unsupported or oversized salvage guidance")
    if guidance["guidance_digest"] != digest({k: v for k, v in guidance.items()
                                               if k != "guidance_digest"}):
        raise HarborError("salvage guidance digest mismatch")
    rebuilt = build_salvage_guidance(guidance["report"], horizon=guidance["horizon"])
    if rebuilt != guidance:
        raise HarborError("salvage guidance legality or route mismatch")
    return {"goal": guidance["goal"], "legal_actions": deepcopy(guidance["legal_actions"]),
            "recommended": deepcopy(guidance["recommended"])}
