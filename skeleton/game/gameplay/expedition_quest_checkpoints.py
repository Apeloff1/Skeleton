"""Replay-authoritative historical quest checkpoints and alternate play.

The caller cannot award NPC gifts, crafting outputs, currency or endings.
Every checkpoint is reconstructed from the canonical source and journal;
digests detect accidental/tampered content, not author identity.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import (
    MAX_ACTIONS, _advance, demo_actions, export_quest, import_quest,
    new_quest, original_quest, resume_quest, simulate_quest, verify_quest,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _integer, _parse_json,
)

TIMELINE_SCHEMA = "skeleton.quest_checkpoint_timeline.v1"
FORK_SCHEMA = "skeleton.quest_checkpoint_fork.v1"
MAX_RECORD_BYTES = 8 * 1024 * 1024


def _bounded(payload: Any) -> None:
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid quest checkpoint JSON") from exc
    if len(raw) > MAX_RECORD_BYTES:
        raise CombatSessionError("quest checkpoint record exceeds size budget")


def _history(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Replay each event once and verify exact saved ancestry and receipts."""
    final = verify_quest(payload)
    current = new_quest(final["source"])
    snapshots = [current]
    for event in final["journal"]:
        current = _advance(current, event["action"])
        if current["journal"][-1] != event:
            raise CombatSessionError("quest checkpoint history mismatch")
        snapshots.append(current)
    if snapshots[-1] != final:
        raise CombatSessionError("quest checkpoint terminal mismatch")
    if len(snapshots) != final["state"]["tick"] + 1:
        raise CombatSessionError("quest checkpoint tick mismatch")
    return final, snapshots


def _snapshot(session: dict[str, Any]) -> dict[str, Any]:
    state = session["state"]
    expedition = state["expedition"]["state"]
    return {
        "tick": state["tick"], "location": state["location"],
        "phase": state["phase"], "ending": state["ending"],
        "state_digest": session["state_digest"],
        "save_digest": dig(session["save"]),
        "event_bus_digest": session["event_bus_digest"],
        "choices": dict(sorted(state["choices"].items())),
        "items": dict(sorted(state["items"].items())),
        "crafted": list(state["crafted"]),
        "combat_phase": expedition["phase"],
        "hero_hp": expedition["hero_hp"],
        "earned_currency": expedition["currency"],
        "combat_inventory": dict(sorted(expedition["inventory"].items())),
    }


def timeline_quest(payload: Any) -> dict[str, Any]:
    final, snapshots = _history(payload)
    result = {
        "schema_version": TIMELINE_SCHEMA,
        "source_digest": final["source_digest"],
        "final_state_digest": final["state_digest"],
        "count": len(snapshots),
        "checkpoints": [_snapshot(s) for s in snapshots],
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def checkpoint_at(payload: Any, tick: int) -> dict[str, Any]:
    final, snapshots = _history(payload)
    _integer(tick, "quest checkpoint tick", 0, len(snapshots) - 1)
    checkpoint = snapshots[tick]
    bundle = export_quest(checkpoint)
    if import_quest(bundle) != checkpoint:
        raise CombatSessionError("quest checkpoint portable roundtrip mismatch")
    if checkpoint["source_digest"] != final["source_digest"]:
        raise CombatSessionError("quest checkpoint source changed")
    return bundle


def compare_quest_paths(left: Any, right: Any) -> dict[str, Any]:
    """Compare only outcomes earned by independently replayed game sessions."""
    first = verify_quest(left)
    second = verify_quest(right)
    if first["source_digest"] != second["source_digest"]:
        raise CombatSessionError("quest comparison source mismatch")
    a, b = first["state"], second["state"]
    keys = sorted(set(a["items"]) | set(b["items"]))
    currency_a = a["expedition"]["state"]["currency"]
    currency_b = b["expedition"]["state"]["currency"]
    report = {
        "source_digest": first["source_digest"],
        "left_state_digest": first["state_digest"],
        "right_state_digest": second["state_digest"],
        "left_tick": a["tick"], "right_tick": b["tick"],
        "left_ending": a["ending"], "right_ending": b["ending"],
        "left_phase": a["phase"], "right_phase": b["phase"],
        "left_location": a["location"], "right_location": b["location"],
        "choice_changes": [
            {"npc_id": npc, "before": a["choices"].get(npc),
             "after": b["choices"].get(npc)}
            for npc in sorted(set(a["choices"]) | set(b["choices"]))
            if a["choices"].get(npc) != b["choices"].get(npc)
        ],
        "item_changes": [
            {"item_id": item, "before": a["items"].get(item, 0),
             "after": b["items"].get(item, 0)}
            for item in keys if a["items"].get(item, 0) != b["items"].get(item, 0)
        ],
        "crafted_before": list(a["crafted"]),
        "crafted_after": list(b["crafted"]),
        "currency_before": currency_a,
        "currency_after": currency_b,
        "currency_delta": currency_b - currency_a,
        "combat_phase_before": a["expedition"]["state"]["phase"],
        "combat_phase_after": b["expedition"]["state"]["phase"],
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def fork_quest(payload: Any, tick: int, actions: Any) -> dict[str, Any]:
    """Fork a historical checkpoint without trusting any caller state mutation."""
    original, snapshots = _history(payload)
    _integer(tick, "quest fork tick", 0, len(snapshots) - 1)
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise CombatSessionError("invalid quest fork actions")
    base = snapshots[tick]
    result = resume_quest(base, actions)
    base_bundle = export_quest(base)
    result_bundle = export_quest(result)
    if import_quest(base_bundle) != base or import_quest(result_bundle) != result:
        raise CombatSessionError("quest fork portable replay mismatch")
    record = {
        "schema_version": FORK_SCHEMA,
        "source_digest": original["source_digest"],
        "original": original,
        "checkpoint_tick": tick,
        "actions": [event["action"] for event in result["journal"][tick:]],
        "checkpoint_bundle": base_bundle,
        "result_bundle": result_bundle,
        "comparison": compare_quest_paths(original, result),
        "fork_state_digest": result["state_digest"],
    }
    record["checksum"] = dig(record)
    _bounded(record)
    return record


def verify_fork(payload: Any) -> dict[str, Any]:
    """Rebuild the entire fork; checksums alone never authorize game rewards."""
    _bounded(payload)
    if type(payload) is not dict or set(payload) != {
        "schema_version", "source_digest", "original", "checkpoint_tick",
        "actions", "checkpoint_bundle", "result_bundle", "comparison",
        "fork_state_digest", "checksum",
    } or payload["schema_version"] != FORK_SCHEMA:
        raise CombatSessionError("invalid quest fork record")
    rebuilt = fork_quest(
        payload["original"], payload["checkpoint_tick"], payload["actions"]
    )
    if rebuilt != payload:
        raise CombatSessionError("quest fork receipt or replay mismatch")
    return import_quest(rebuilt["result_bundle"])


def original_fork() -> dict[str, Any]:
    """Playable original beacon quest with a genuinely different ending."""
    actions = demo_actions()
    full = simulate_quest(original_quest(), actions)
    alternate = [
        {"kind": "talk", "npc_id": "guide", "decision": "decline"},
        *[action for action in actions[1:]
          if action["kind"] != "craft" and action["kind"] != "finish"],
        {"kind": "finish", "ending_id": "quiet_victory"},
    ]
    return fork_quest(full, 0, alternate)


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-checkpoints")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--source-digest", default=argparse.SUPPRESS)
    for name in ("timeline", "checkpoint", "fork", "compare"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--session-json", required=True)
        cmd.add_argument("--source-digest", default=argparse.SUPPRESS)
        if name in ("checkpoint", "fork"):
            cmd.add_argument("--tick", type=int, required=True)
        if name == "fork":
            cmd.add_argument("--actions-json", required=True)
        if name == "compare":
            cmd.add_argument("--other-session-json", required=True)
    check = commands.add_parser("verify-fork")
    check.add_argument("--record-json", required=True)
    check.add_argument("--source-digest", default=argparse.SUPPRESS)
    parser.add_argument("--source-digest")
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_fork()
        elif args.command == "verify-fork":
            verified = verify_fork(_parse_json(args.record_json, "quest fork"))
            result = {"ok": True, "source_digest": verified["source_digest"],
                      "state_digest": verified["state_digest"],
                      "ending": verified["state"]["ending"]}
        else:
            session = _parse_json(args.session_json, "quest session")
            if args.command == "timeline":
                result = timeline_quest(session)
            elif args.command == "checkpoint":
                result = checkpoint_at(session, args.tick)
            elif args.command == "compare":
                result = compare_quest_paths(
                    session, _parse_json(args.other_session_json, "other quest")
                )
            else:
                result = fork_quest(
                    session, args.tick,
                    _parse_json(args.actions_json, "quest fork actions"),
                )
        if args.source_digest is not None:
            if (type(args.source_digest) is not str
                    or len(args.source_digest) != 64
                    or any(c not in "0123456789abcdef" for c in args.source_digest)
                    or result["source_digest"] != args.source_digest):
                raise CombatSessionError("trusted quest source digest mismatch")
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
