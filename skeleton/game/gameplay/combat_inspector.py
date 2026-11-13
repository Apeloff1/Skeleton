"""Replay-verified, source-bound offline combat timeline inspection.

Inspects canonical game turns without executing authored code or trusting
serialized HP/damage values. A comparison is permitted only for identical
normalized authored source. Results are diagnostic evidence, not signatures.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _advance, _parse_json, new_session,
    verify_session,
)

INSPECTOR_SCHEMA = "skeleton.combat_inspector.v1"


def inspect_session(payload: Any) -> dict[str, Any]:
    """Recompute every actual turn and expose immutable state transitions."""
    verified = verify_session(payload)
    cursor = new_session(verified["scenario"])
    timeline: list[dict[str, Any]] = []
    for event in verified["journal"]:
        before = cursor["state"]
        cursor = _advance(cursor, event["action"])
        after = cursor["state"]
        changes = {
            actor_id: {
                "hp_before": before["actors"][actor_id]["hp"],
                "hp_after": after["actors"][actor_id]["hp"],
                "guard_before": before["actors"][actor_id]["guard"],
                "guard_after": after["actors"][actor_id]["guard"],
            }
            for actor_id in sorted(before["actors"])
            if before["actors"][actor_id] != after["actors"][actor_id]
        }
        timeline.append({
            "turn": event["sequence"],
            "action": event["action"],
            "before_digest": event["before"],
            "after_digest": event["after"],
            "receipt": event["receipt"],
            "changes": changes,
            "phase": after["phase"],
            "winner": after["winner"],
        })
    if cursor != verified:
        raise CombatSessionError("timeline reconstruction differs from save")
    return {
        "schema_version": INSPECTOR_SCHEMA,
        "world_id": verified["scenario"]["world_id"],
        "encounter_id": verified["scenario"]["encounter_id"],
        "source_digest": verified["source_digest"],
        "state_digest": verified["state_digest"],
        "event_bus_digest": verified["event_bus_digest"],
        "turn_count": len(timeline),
        "phase": verified["state"]["phase"],
        "winner": verified["state"]["winner"],
        "timeline": timeline,
    }


def compare_sessions(left: Any, right: Any) -> dict[str, Any]:
    """Compare replayed branches, not potentially forged unverified snapshots."""
    a = verify_session(left)
    b = verify_session(right)
    if a["source_digest"] != b["source_digest"]:
        raise CombatSessionError("cannot compare different authored combat sources")
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
        "schema_version": INSPECTOR_SCHEMA,
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
        prog="python -m skeleton.game.gameplay.combat_inspector",
        description="Inspect replay-verified local combat sessions offline",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    single = sub.add_parser("inspect")
    single.add_argument("--session-json", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--left-json", required=True)
    compare.add_argument("--right-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "inspect":
            result = inspect_session(_parse_json(args.session_json, "session"))
        else:
            result = compare_sessions(
                _parse_json(args.left_json, "left session"),
                _parse_json(args.right_json, "right session"),
            )
    except CombatSessionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
