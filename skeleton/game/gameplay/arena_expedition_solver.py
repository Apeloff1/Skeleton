"""Bounded, replay-verifiable planning for authored tactical expeditions.

This is a deterministic *search* over the real expedition runtime, not a
prediction of combat success. Budget exhaustion is explicitly inconclusive.
No network, model inference, fabricated rewards or privileged writes occur.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_expedition import (
    MAX_ACTIONS, _advance, new_expedition, original_expedition, verify_expedition,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _integer, _parse_json,
)

SCHEMA = "skeleton.arena_expedition_plan.v1"
MAX_STATES = 256
MAX_DEPTH = 24


def _key(session: dict[str, Any]) -> tuple[Any, ...]:
    """Collapse only states with equivalent future gameplay opportunities."""
    state = session["state"]
    return (
        state["next_index"], state["hero_hp"], state["currency"],
        state["phase"], tuple(sorted(state["inventory"].items())),
        tuple(sorted(state["purchased"].items())),
    )


def _choices(session: dict[str, Any]) -> list[dict[str, str]]:
    state, source = session["state"], session["source"]
    if state["phase"] != "active":
        return []
    actions: list[dict[str, str]] = []
    if state["next_index"] < len(source["arenas"]) and state["hero_hp"] > 0:
        actions.append({"kind": "fight"})
    if sum(state["inventory"].values()) < 16:
        for item in source["shop"]:
            item_id = item["id"]
            if (
                state["currency"] >= item["price"]
                and state["purchased"].get(item_id, 0) < item["stock"]
            ):
                actions.append({"kind": "buy", "item_id": item_id})
    hero = next(
        actor for actor in source["arenas"][0]["arena"]["actors"]
        if actor["id"] == source["hero_id"]
    )
    if state["hero_hp"] < hero["max_hp"]:
        for item_id in sorted(state["inventory"]):
            if state["inventory"][item_id] > 0:
                actions.append({"kind": "use", "item_id": item_id})
    return sorted(actions, key=lambda x: (x["kind"], x.get("item_id", "")))


def plan_expedition(source: Any = None, *, session: Any = None,
                    max_states: int = 128, max_depth: int = 16) -> dict[str, Any]:
    """Breadth-first search for the shortest *actually replayable* victory.

    The source or save must be supplied, never both. No tactical action is
    synthesized: only canonical automatic combat, purchases and item use are
    searched. A capped search is not proof that an ending is unreachable.
    """
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one expedition source or save")
    _integer(max_states, "expedition search state budget", 1, MAX_STATES)
    _integer(max_depth, "expedition search depth budget", 1, MAX_DEPTH)
    start = new_expedition(source) if session is None else verify_expedition(session)
    base = {
        "schema_version": SCHEMA,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "max_states": max_states, "max_depth": max_depth,
    }

    def report(status: str, actions: tuple[dict[str, str], ...],
               explored: int, truncated: bool,
               terminal: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            **base, "status": status, "actions": list(actions),
            "explored": explored, "budget_exhausted": truncated,
            "final_state_digest": (
                terminal["state_digest"] if terminal is not None else None
            ),
            "final_phase": (
                terminal["state"]["phase"] if terminal is not None else None
            ),
            "hero_hp": (
                terminal["state"]["hero_hp"] if terminal is not None else None
            ),
            "currency": (
                terminal["state"]["currency"] if terminal is not None else None
            ),
        }

    if start["state"]["phase"] == "won":
        return report("found", (), 0, False, start)
    if start["state"]["phase"] != "active":
        return report("unreachable", (), 0, False)
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
        current, history = frontier.popleft()
        explored += 1
        if len(history) >= max_depth or len(current["journal"]) >= MAX_ACTIONS:
            truncated = True
            continue
        for action in _choices(current):
            try:
                candidate = _advance(current, action)
            except CombatSessionError:
                # A legal-looking purchase/fight can still be rejected by
                # canonical combat rules. Never assume success.
                continue
            route = (*history, action)
            if candidate["state"]["phase"] == "won":
                # Validate the complete witness, including prior save lineage.
                replayed = candidate
                if session is None:
                    replayed = new_expedition(start["source"])
                else:
                    replayed = verify_expedition(start)
                for step in route:
                    if replayed is candidate:
                        break
                    replayed = _advance(replayed, step)
                if replayed != candidate:
                    raise CombatSessionError("expedition solver witness mismatch")
                return report("found", route, explored, False, candidate)
            if candidate["state"]["phase"] != "active":
                continue
            key = _key(candidate)
            if key not in seen:
                seen.add(key)
                frontier.append((candidate, route))
    return report("inconclusive" if truncated else "unreachable", (),
                  explored, truncated)


def verify_plan(payload: Any, *, source: Any = None,
                session: Any = None) -> dict[str, Any]:
    """Recompute a planning receipt; a digest is not an authenticity claim."""
    fields = {
        "schema_version", "source_digest", "initial_state_digest",
        "max_states", "max_depth", "status", "actions", "explored",
        "budget_exhausted", "final_state_digest", "final_phase",
        "hero_hp", "currency",
    }
    if (
        type(payload) is not dict or set(payload) != fields
        or payload["schema_version"] != SCHEMA
    ):
        raise CombatSessionError("invalid expedition plan receipt")
    expected = plan_expedition(
        source, session=session, max_states=payload["max_states"],
        max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise CombatSessionError("expedition plan replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-expedition-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Find a replayable original expedition route")
    for name, fields in {
        "plan": ("source-json",),
        "resume": ("session-json",),
        "verify": ("source-json", "plan-json"),
        "verify-resume": ("session-json", "plan-json"),
    }.items():
        command = sub.add_parser(name)
        for field in fields:
            command.add_argument("--" + field, required=True)
        if name in ("plan", "resume"):
            command.add_argument("--max-states", type=int, default=128)
            command.add_argument("--max-depth", type=int, default=16)
    args = parser.parse_args(list(argv))
    try:
        def read(name: str) -> Any:
            return _parse_json(getattr(args, name.replace("-", "_")), name)
        if args.command == "demo":
            result = plan_expedition(original_expedition())
        elif args.command == "plan":
            result = plan_expedition(
                read("source-json"), max_states=args.max_states,
                max_depth=args.max_depth,
            )
        elif args.command == "resume":
            result = plan_expedition(
                session=read("session-json"), max_states=args.max_states,
                max_depth=args.max_depth,
            )
        elif args.command == "verify":
            result = verify_plan(read("plan-json"), source=read("source-json"))
        else:
            result = verify_plan(read("plan-json"), session=read("session-json"))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
