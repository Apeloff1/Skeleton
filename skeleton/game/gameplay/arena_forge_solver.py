"""Deterministic bounded equipment-and-combat route planning.

The planner executes canonical arena forging and tactical fights. It never
credits unearned materials, assumes an outcome, or treats a truncated search
as evidence that a playable run cannot be won.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_forge_run import (
    _advance, new_forge, original_forge, verify_forge,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _integer, _parse_json,
)

SCHEMA = "skeleton.arena_forge_plan.v1"
MAX_STATES = 512
MAX_DEPTH = 24


def _key(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    state = snapshot["state"]
    return (state["next_index"], state["hero_hp"], state["phase"],
            tuple(sorted(state["materials"].items())),
            tuple(sorted(state["gear"].items())), state["equipped"])


def _options(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    state, source = snapshot["state"], snapshot["source"]
    actions = []
    if state["next_index"] < len(source["stages"]) and state["hero_hp"] > 0:
        actions.append({"kind": "fight"})
    for recipe in source["recipes"]:
        key = recipe["id"]
        if key not in state["gear"] and all(
            state["materials"].get(c["id"], 0) >= c["quantity"]
            for c in recipe["costs"]
        ):
            actions.append({"kind": "craft", "recipe_id": key})
    for key in sorted(state["gear"]):
        if key != state["equipped"]:
            actions.append({"kind": "equip", "recipe_id": key})
    if state["equipped"] is not None:
        actions.append({"kind": "unequip"})
    return sorted(actions, key=lambda x: (x["kind"], x.get("recipe_id", "")))


def plan_forge(source: Any = None, *, session: Any = None,
               max_states: int = 128, max_depth: int = 16) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one forge source or save")
    _integer(max_states, "search state budget", 1, MAX_STATES)
    _integer(max_depth, "search depth budget", 1, MAX_DEPTH)
    start = new_forge(source) if session is None else verify_forge(session)
    base = {"schema_version": SCHEMA,
            "source_digest": start["source_digest"],
            "initial_state_digest": start["state_digest"],
            "max_states": max_states, "max_depth": max_depth}
    phase = start["state"]["phase"]
    if phase != "active":
        return {**base, "status": "found" if phase == "won" else "unreachable",
                "actions": [], "explored": 0, "budget_exhausted": False,
                "final_state_digest": start["state_digest"] if phase == "won" else None}
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
            phase = next_snapshot["state"]["phase"]
            if phase == "won":
                return {**base, "status": "found",
                        "actions": list(candidate), "explored": explored,
                        "budget_exhausted": False,
                        "final_state_digest": next_snapshot["state_digest"]}
            if phase != "active":
                continue
            key = _key(next_snapshot)
            if key not in seen:
                seen.add(key)
                frontier.append((next_snapshot, candidate))
    return {**base, "status": "inconclusive" if truncated else "unreachable",
            "actions": [], "explored": explored, "budget_exhausted": truncated,
            "final_state_digest": None}


def verify_plan(payload: Any, *, source: Any = None,
                session: Any = None) -> dict[str, Any]:
    if type(payload) is not dict or set(payload) != {
        "schema_version", "source_digest", "initial_state_digest",
        "max_states", "max_depth", "status", "actions", "explored",
        "budget_exhausted", "final_state_digest",
    } or payload["schema_version"] != SCHEMA:
        raise CombatSessionError("invalid forge plan receipt")
    expected = plan_forge(
        source, session=session, max_states=payload["max_states"],
        max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise CombatSessionError("forge plan replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-forge-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name, fields in {
        "plan": ("source-json",), "resume": ("session-json",),
        "verify": ("source-json", "plan-json"),
    }.items():
        command = sub.add_parser(name)
        for field in fields:
            command.add_argument("--" + field, required=True)
        if name != "verify":
            command.add_argument("--max-states", type=int, default=128)
            command.add_argument("--max-depth", type=int, default=16)
    args = parser.parse_args(list(argv))
    try:
        read = lambda name: _parse_json(
            getattr(args, name.replace("-", "_")), name,
        )
        if args.command == "demo":
            result = plan_forge(original_forge())
        elif args.command == "plan":
            result = plan_forge(read("source-json"), max_states=args.max_states,
                                max_depth=args.max_depth)
        elif args.command == "resume":
            result = plan_forge(session=read("session-json"),
                                max_states=args.max_states,
                                max_depth=args.max_depth)
        else:
            result = verify_plan(read("plan-json"), source=read("source-json"))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
