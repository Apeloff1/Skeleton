"""Bounded deterministic navigation from a verified Lantern Quay checkpoint.

Only legal move/wait transitions are explored. NPC motion is simulated by the
canonical engine, so proposed routes cannot pass through an occupied tile.
The portable route carries its source, history, result, and replay proof.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _integer, _keys, canonical, digest,
    step, verify_bundle,
)
from .harbor_crafting_sessions import resume_bundle

SCHEMA = "skeleton.game.harbor.route.v1"
MAX_ROUTE_STEPS = 64
MAX_ROUTE_NODES = 8192
MAX_ROUTE_BYTES = MAX_BUNDLE_BYTES * 3
FIELDS = {
    "schema", "root", "goal", "max_steps", "actions", "result",
    "explored", "route_digest",
}
DIRECTIONS = ("north", "east", "south", "west")
MOVES = tuple({"op": "move", "direction": direction} for direction in DIRECTIONS)
MOVES += ({"op": "wait"},)


def _goal(source: dict[str, Any], goal: Any) -> list[int]:
    if not isinstance(goal, list) or len(goal) != 2:
        raise HarborError("route goal must be a coordinate pair")
    x = _integer(goal[0], 0, len(source["map"][0]) - 1, "route x")
    y = _integer(goal[1], 0, len(source["map"]) - 1, "route y")
    if source["map"][y][x] != ".":
        raise HarborError("route goal is blocked")
    return [x, y]


def _key(state: dict[str, Any]) -> tuple[int, int, int, int, int]:
    # NPC motion can depend on earlier collision, not merely tick modulo route.
    return (
        state["tick"], state["pos"][0], state["pos"][1],
        state["npc_pos"][0], state["npc_pos"][1],
    )


def plan_route(
    root: Any,
    goal: Any,
    *,
    expected_terminal_digest: str,
    max_steps: int = MAX_ROUTE_STEPS,
) -> dict[str, Any]:
    """Find the shortest legal route, preserving the complete save history.

    A bounded failure is explicit: no fabricated path, teleport, or partial
    result is exported when the goal cannot be reached.
    """
    state = verify_bundle(root)
    source = root["source"]
    target = _goal(source, goal)
    _integer(max_steps, 1, MAX_ROUTE_STEPS, "route step budget")
    if (
        not isinstance(expected_terminal_digest, str)
        or expected_terminal_digest != root["terminal_digest"]
    ):
        raise HarborError("stale route checkpoint")
    if state["ending"] is not None:
        raise HarborError("cannot navigate after ending")
    remaining = source["max_ticks"] - state["tick"]
    horizon = min(max_steps, remaining)
    nodes: list[tuple[dict[str, Any], int, dict[str, str] | None]] = [
        (state, -1, None)
    ]
    queue = deque([0])
    seen = {_key(state)}
    found: int | None = None
    while queue:
        index = queue.popleft()
        current = nodes[index][0]
        if current["pos"] == target:
            found = index
            break
        if current["tick"] - state["tick"] >= horizon:
            continue
        for action in MOVES:
            try:
                successor = step(source, current, action)
            except HarborError:
                continue
            identity = _key(successor)
            if identity in seen:
                continue
            if len(nodes) >= MAX_ROUTE_NODES:
                raise HarborError("route search node budget exceeded")
            seen.add(identity)
            nodes.append((successor, index, action))
            queue.append(len(nodes) - 1)
    if found is None:
        raise HarborError("route unavailable within bounded search")
    actions: list[dict[str, str]] = []
    cursor = found
    while nodes[cursor][1] != -1:
        current, parent, action = nodes[cursor]
        if action is None or parent >= cursor:
            raise HarborError("invalid route reconstruction")
        actions.append(deepcopy(action))
        cursor = parent
    actions.reverse()
    result = resume_bundle(
        root, actions, expected_terminal_digest=expected_terminal_digest
    )
    if result["state"]["pos"] != target:
        raise HarborError("route failed to reach goal")
    report = {
        "schema": SCHEMA,
        "root": deepcopy(root),
        "goal": target,
        "max_steps": max_steps,
        "actions": actions,
        "result": result,
        "explored": len(nodes),
    }
    report["route_digest"] = digest(report)
    if len(canonical(report)) > MAX_ROUTE_BYTES:
        raise HarborError("route report exceeds byte limit")
    return report


def verify_route(report: Any) -> dict[str, Any]:
    """Replay navigation from original authored world and reject resealed lies."""
    _keys(report, FIELDS, "route report")
    if report["schema"] != SCHEMA or len(canonical(report)) > MAX_ROUTE_BYTES:
        raise HarborError("unsupported or oversized route report")
    if report["route_digest"] != digest({
        key: value for key, value in report.items()
        if key != "route_digest"
    }):
        raise HarborError("route digest mismatch")
    root = report["root"]
    if not isinstance(root, dict):
        raise HarborError("route root missing")
    rebuilt = plan_route(
        root, report["goal"],
        expected_terminal_digest=root.get("terminal_digest"),
        max_steps=report["max_steps"],
    )
    if rebuilt != report:
        raise HarborError("route replay mismatch")
    return {
        "source_digest": root["source_digest"],
        "start_terminal_digest": root["terminal_digest"],
        "terminal_digest": rebuilt["result"]["terminal_digest"],
        "goal": deepcopy(rebuilt["goal"]),
        "steps": len(rebuilt["actions"]),
        "explored": rebuilt["explored"],
    }
