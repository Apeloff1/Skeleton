"""Replay-derived offline tactical arena timeline and branch comparison.

All visible events and coordinates are reconstructed from verified source and
actions; untrusted snapshot fields cannot manufacture a combat result.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _parse_json,
)
from skeleton.game.gameplay.tactical_arena import (
    _advance, new_arena, verify_arena,
)

SCHEMA = "skeleton.arena_inspector.v1"


def inspect_session(payload: Any) -> dict[str, Any]:
    verified = verify_arena(payload)
    cursor = new_arena(verified["source"])
    timeline = []
    for event in verified["journal"]:
        prior = cursor["state"]
        cursor = _advance(cursor, event["action"])
        after = cursor["state"]
        changed = {}
        for actor_id, status in after["actors"].items():
            previous = prior["actors"][actor_id]
            if previous != status:
                changed[actor_id] = {
                    "before": {
                        "hp": previous["hp"], "guard": previous["guard"],
                        "position": list(previous["position"]),
                    },
                    "after": {
                        "hp": status["hp"], "guard": status["guard"],
                        "position": list(status["position"]),
                    },
                }
        timeline.append({
            "sequence": event["sequence"],
            "action": event["action"],
            "receipt": event["receipt"],
            "state_before": event["before"],
            "state_after": event["after"],
            "changed_actors": changed,
            "phase": after["phase"],
            "winner": after["winner"],
        })
    return {
        "schema_version": SCHEMA,
        "world_id": verified["source"]["world_id"],
        "arena_id": verified["source"]["arena_id"],
        "source_digest": verified["source_digest"],
        "state_digest": verified["state_digest"],
        "event_bus_digest": verified["event_bus_digest"],
        "phase": verified["state"]["phase"],
        "winner": verified["state"]["winner"],
        "turn_count": len(timeline),
        "timeline": timeline,
    }


def compare_sessions(left: Any, right: Any) -> dict[str, Any]:
    a = verify_arena(left)
    b = verify_arena(right)
    if a["source_digest"] != b["source_digest"]:
        raise CombatSessionError("cannot compare different authored arena sources")
    common = 0
    while (
        common < min(len(a["journal"]), len(b["journal"]))
        and a["journal"][common] == b["journal"][common]
    ):
        common += 1
    if a == b:
        relationship = "identical"
    elif common == len(a["journal"]) or common == len(b["journal"]):
        relationship = "prefix"
    else:
        relationship = "divergent"
    return {
        "schema_version": SCHEMA,
        "source_digest": a["source_digest"],
        "relationship": relationship,
        "common_turns": common,
        "first_divergent_turn": (
            common if relationship == "divergent" else None
        ),
        "left": {
            "turns": len(a["journal"]), "phase": a["state"]["phase"],
            "winner": a["state"]["winner"],
            "state_digest": a["state_digest"],
        },
        "right": {
            "turns": len(b["journal"]), "phase": b["state"]["phase"],
            "winner": b["state"]["winner"],
            "state_digest": b["state_digest"],
        },
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.game.gameplay.arena_inspector"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--session-json", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--left-json", required=True)
    compare.add_argument("--right-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "inspect":
            result = inspect_session(_parse_json(args.session_json, "arena save"))
        else:
            result = compare_sessions(
                _parse_json(args.left_json, "left arena save"),
                _parse_json(args.right_json, "right arena save"),
            )
    except (CombatSessionError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
