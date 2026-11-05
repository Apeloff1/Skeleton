"""Bounded deterministic shortest-route solver for playable scene circuits.

The search uses actual circuit transitions and never invents unlocks or
inventory. Exhausted search budgets are inconclusive, not proof of defeat.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_circuit import (
    _advance, new_circuit, original_circuit, verify_circuit,
)
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _json, _scene,
)

SCHEMA = "skeleton.scene_circuit_plan.v1"
MAX_STATES = 4096
MAX_DEPTH = 96


def _key(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    state = snapshot["state"]
    scene = state["scene"]["state"]
    return (scene["scene_id"], tuple(scene["inventory"]),
            tuple(scene["collected"]), tuple(sorted(state["switches"].items())))


def _options(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    state = snapshot["state"]
    world = snapshot["source"]["world"]
    current = _scene(world, state["scene"]["state"]["scene_id"])
    actions = []
    for switch in snapshot["source"]["switches"]:
        if switch["scene_id"] == current["id"]:
            actions.append({"kind": "toggle", "switch_id": switch["id"]})
    collected = set(state["scene"]["state"]["collected"])
    for pickup in current["pickups"]:
        if current["id"] + ":" + pickup["id"] not in collected:
            actions.append({"kind": "collect", "pickup_id": pickup["id"]})
    inventory = set(state["scene"]["state"]["inventory"])
    for edge in current["exits"]:
        if edge["requires_item"] is not None and edge["requires_item"] not in inventory:
            continue
        gate = next((g for g in snapshot["source"]["gates"]
                     if g["scene_id"] == current["id"]
                     and g["exit_id"] == edge["id"]), None)
        if gate is not None and (
            any(not state["switches"][x] for x in gate["requires_on"])
            or any(state["switches"][x] for x in gate["requires_off"])
        ):
            continue
        actions.append({"kind": "travel", "exit_id": edge["id"]})
    return sorted(actions, key=lambda x: (x["kind"],
                  x.get("exit_id", x.get("pickup_id", x.get("switch_id", "")))))


def plan_circuit(source: Any = None, *, session: Any = None,
                 max_states: int = 1024, max_depth: int = 64) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one circuit source or save")
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid circuit search state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid circuit search depth budget")
    start = new_circuit(source) if session is None else verify_circuit(session)
    initial = start["state_digest"]
    origin = start["source_digest"]
    base = {"schema_version": SCHEMA, "source_digest": origin,
            "initial_state_digest": initial, "max_states": max_states,
            "max_depth": max_depth}
    phase = start["state"]["scene"]["state"]["phase"]
    if phase != "active":
        return {**base, "status": "found" if phase == "won" else "unreachable",
                "final_state_digest": initial if phase == "won" else None,
                "actions": [], "explored": 0, "budget_exhausted": False}
    frontier: deque[tuple[dict[str, Any], tuple[dict[str, str], ...]]] = deque(
        [(start, ())]
    )
    seen = {_key(start)}
    explored = 0
    truncated = False
    while frontier:
        if explored >= max_states:
            truncated = True
            break
        snapshot, actions = frontier.popleft()
        explored += 1
        if len(actions) >= max_depth:
            truncated = True
            continue
        for action in _options(snapshot):
            next_snapshot = _advance(snapshot, action)
            candidate = (*actions, action)
            phase = next_snapshot["state"]["scene"]["state"]["phase"]
            if phase == "won":
                return {**base, "status": "found",
                        "final_state_digest": next_snapshot["state_digest"],
                        "actions": list(candidate), "explored": explored,
                        "budget_exhausted": False}
            if phase != "active":
                continue
            key = _key(next_snapshot)
            if key not in seen:
                seen.add(key)
                frontier.append((next_snapshot, candidate))
    return {**base, "status": "inconclusive" if truncated else "unreachable",
            "final_state_digest": None, "actions": [], "explored": explored,
            "budget_exhausted": truncated}


def verify_plan(payload: Any, *, source: Any = None,
                session: Any = None) -> dict[str, Any]:
    if type(payload) is not dict or set(payload) != {
        "schema_version", "source_digest", "initial_state_digest",
        "max_states", "max_depth", "status", "final_state_digest",
        "actions", "explored", "budget_exhausted",
    } or payload["schema_version"] != SCHEMA:
        raise SceneTravelError("invalid circuit plan receipt")
    rebuilt = plan_circuit(
        source, session=session, max_states=payload["max_states"],
        max_depth=payload["max_depth"],
    )
    if rebuilt != payload:
        raise SceneTravelError("circuit plan replay mismatch")
    return rebuilt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-circuit-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name, fields in {
        "plan": ("source-json",),
        "resume": ("session-json",),
        "verify": ("source-json", "plan-json"),
    }.items():
        command = sub.add_parser(name)
        for field in fields:
            command.add_argument("--" + field, required=True)
        if name != "verify":
            command.add_argument("--max-states", type=int, default=1024)
            command.add_argument("--max-depth", type=int, default=64)
    args = parser.parse_args(list(argv))
    try:
        read = lambda name: _json(getattr(args, name.replace("-", "_")), name,
                                  max_bytes=2 * 1024 * 1024)
        if args.command == "demo":
            source, _ = original_circuit()
            result = plan_circuit(source)
        elif args.command == "plan":
            result = plan_circuit(read("source-json"),
                                  max_states=args.max_states,
                                  max_depth=args.max_depth)
        elif args.command == "resume":
            result = plan_circuit(session=read("session-json"),
                                  max_states=args.max_states,
                                  max_depth=args.max_depth)
        else:
            result = verify_plan(read("plan-json"), source=read("source-json"))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
