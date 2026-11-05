"""Bounded source-bound shortest quest route over NPC, crafting and combat.

Every candidate action is executed by the canonical quest engine. A bounded
search that cannot finish is inconclusive, never proof of an impossible ending.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import (
    _advance, export_quest, import_quest, new_quest, original_quest,
    resume_quest, verify_quest,
)
from skeleton.game.gameplay.expedition_quest_interactive import legal_quest_actions
from skeleton.game.gameplay.turn_combat import CombatSessionError, _id, _parse_json

SCHEMA = "skeleton.expedition_quest_route.v1"
MAX_STATES = 2048
MAX_DEPTH = 32


def _limits(max_states: int, max_depth: int) -> None:
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise CombatSessionError("invalid quest route state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise CombatSessionError("invalid quest route depth budget")


def _result(start: dict[str, Any], target: str, status: str,
            actions: list[dict[str, Any]], explored: int, truncated: bool,
            final: dict[str, Any] | None, max_states: int,
            max_depth: int) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA, "status": status,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "target_ending": target,
        "final_state_digest": final["state_digest"] if final is not None else None,
        "portable_checksum": (
            export_quest(final)["checksum"] if final is not None else None
        ),
        "actions": actions, "explored": explored,
        "budget_exhausted": truncated,
        "max_states": max_states, "max_depth": max_depth,
    }
    return result


def plan_quest(source: Any = None, *, session: Any = None,
               target_ending: str, max_states: int = 256,
               max_depth: int = 20) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one quest source or checkpoint")
    _limits(max_states, max_depth)
    start = new_quest(source) if session is None else verify_quest(session)
    target = _id(target_ending, "target_ending")
    if target not in {ending["id"] for ending in start["source"]["endings"]}:
        raise CombatSessionError("unknown authored quest ending")
    if start["state"]["phase"] == "finished":
        matched = start["state"]["ending"] == target
        return _result(start, target, "found" if matched else "unreachable",
                       [], 0, False, start if matched else None,
                       max_states, max_depth)
    queue = deque([(start, ())])
    seen = {start["state_digest"]}
    explored = 0
    truncated = False
    while queue:
        if explored >= max_states:
            truncated = True
            break
        current, actions = queue.popleft()
        explored += 1
        if len(actions) >= max_depth:
            if legal_quest_actions(current):
                truncated = True
            continue
        for action in legal_quest_actions(current):
            try:
                advanced = _advance(current, action)
            except CombatSessionError:
                continue
            path = (*actions, action)
            if (advanced["state"]["phase"] == "finished"
                    and advanced["state"]["ending"] == target):
                bundle = export_quest(advanced)
                if import_quest(bundle) != advanced:
                    raise CombatSessionError("quest route portable replay mismatch")
                return _result(start, target, "found", list(path), explored,
                               False, advanced, max_states, max_depth)
            if advanced["state"]["phase"] != "active":
                continue
            if advanced["state_digest"] not in seen:
                seen.add(advanced["state_digest"])
                queue.append((advanced, path))
    return _result(start, target,
                   "inconclusive" if truncated else "unreachable",
                   [], explored, truncated, None, max_states, max_depth)


def verify_plan(plan: Any, *, source: Any = None,
                session: Any = None) -> dict[str, Any]:
    """Recompute the bounded search and replay the complete portable witness."""
    if type(plan) is not dict or plan.get("schema_version") != SCHEMA:
        raise CombatSessionError("invalid quest route receipt")
    if plan.get("status") != "found":
        raise CombatSessionError("only found routes have playable witnesses")
    _limits(plan.get("max_states"), plan.get("max_depth"))
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one quest source or checkpoint")
    start = new_quest(source) if session is None else verify_quest(session)
    expected = plan_quest(
        session=start, target_ending=plan.get("target_ending"),
        max_states=plan["max_states"], max_depth=plan["max_depth"],
    )
    if expected != plan:
        raise CombatSessionError("quest route search receipt mismatch")
    final = resume_quest(start, plan["actions"])
    if (final["state"]["phase"] != "finished"
            or final["state"]["ending"] != plan["target_ending"]
            or final["state_digest"] != plan["final_state_digest"]):
        raise CombatSessionError("quest route replay witness mismatch")
    if export_quest(final)["checksum"] != plan["portable_checksum"]:
        raise CombatSessionError("quest route export witness mismatch")
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-expedition-route")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    parser.add_argument("--ending-id", default="beacon_lit")
    parser.add_argument("--max-states", type=int, default=256)
    parser.add_argument("--max-depth", type=int, default=20)
    parser.add_argument("--verify-json")
    args = parser.parse_args(list(argv))
    try:
        source = (original_quest() if args.demo else
                  _parse_json(args.source_json, "quest source")
                  if args.source_json is not None else None)
        saved = (_parse_json(args.session_json, "quest checkpoint")
                 if args.session_json is not None else None)
        if args.verify_json is not None:
            final = verify_plan(
                _parse_json(args.verify_json, "quest route receipt"),
                source=source, session=saved,
            )
            result = {"ok": True, "ending": final["state"]["ending"],
                      "state_digest": final["state_digest"]}
        else:
            result = plan_quest(
                source, session=saved, target_ending=args.ending_id,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
