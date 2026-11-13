"""Replay-proven mission consequence and alternate-ending audit.

Every choice, reputation delta and quest award is derived by replaying the
canonical mission engine. Comparison never trusts client-provided reputation,
quest completions or claimed endings. Portable receipts are not signatures.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_mission import (
    MAX_BYTES, _advance, demo_actions, new_mission, original_mission,
    simulate_mission, verify_mission,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _object
from skeleton.game.gameplay.scene_atlas import _strict_json

SCHEMA = "skeleton.scene_mission_consequences.v1"
BUNDLE = "skeleton.scene_mission_consequences_bundle.v1"


def _size(payload: Any) -> None:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid mission consequences JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise SceneTravelError("mission consequences exceed 2 MiB")


def inspect_consequences(payload: Any) -> dict[str, Any]:
    session = verify_mission(payload)
    cursor = new_mission(session["source"])
    history = []
    for recorded in session["journal"]:
        before = cursor["state"]
        cursor = _advance(cursor, recorded["action"])
        after = cursor["state"]
        earned = sorted(set(after["missions"]) - set(before["missions"]))
        history.append({
            "sequence": recorded["sequence"], "action": recorded["action"],
            "before_state_digest": recorded["before"],
            "after_state_digest": recorded["after"],
            "event_receipt": recorded["receipt"],
            "reputation_before": before["reputation"],
            "reputation_after": after["reputation"],
            "reputation_delta": after["reputation"] - before["reputation"],
            "missions_earned": earned,
            "choice_resolved": (
                {"choice_id": recorded["action"]["choice_id"],
                 "option_id": recorded["action"]["option_id"]}
                if recorded["action"]["kind"] == "choose" else None
            ),
            "scene_before": before["scene"]["state"]["scene_id"],
            "scene_after": after["scene"]["state"]["scene_id"],
            "ending": after["ending"],
        })
    if cursor != session:
        raise SceneTravelError("mission consequence replay mismatch")
    state = session["state"]
    report = {
        "schema_version": SCHEMA, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "event_bus_digest": session["event_bus_digest"],
        "director_id": session["source"]["director_id"],
        "turns": len(history), "reputation": state["reputation"],
        "choices": dict(sorted(state["choices"].items())),
        "missions": list(state["missions"]),
        "phase": state["phase"], "ending": state["ending"],
        "scene_phase": state["scene"]["state"]["phase"],
        "history": history,
    }
    result = {**report, "receipt": dig(report)}
    _size(result)
    return result


def compare_consequences(left: Any, right: Any) -> dict[str, Any]:
    a, b = verify_mission(left), verify_mission(right)
    if a["source_digest"] != b["source_digest"]:
        raise SceneTravelError("mission comparison needs identical authored source")
    left_report = inspect_consequences(a)
    right_report = inspect_consequences(b)
    common = 0
    while (common < min(len(a["journal"]), len(b["journal"]))
           and a["journal"][common] == b["journal"][common]):
        common += 1
    relation = ("identical" if a == b else
                "prefix" if common in (len(a["journal"]), len(b["journal"]))
                else "divergent")
    choices_a, choices_b = a["state"]["choices"], b["state"]["choices"]
    differences = [
        {"choice_id": key, "left": choices_a.get(key), "right": choices_b.get(key)}
        for key in sorted(set(choices_a) | set(choices_b))
        if choices_a.get(key) != choices_b.get(key)
    ]
    report = {
        "schema_version": SCHEMA, "source_digest": a["source_digest"],
        "relationship": relation, "common_turns": common,
        "choice_differences": differences,
        "reputation_delta_right_minus_left": (
            right_report["reputation"] - left_report["reputation"]
        ),
        "missions_only_left": sorted(set(left_report["missions"]) -
                                     set(right_report["missions"])),
        "missions_only_right": sorted(set(right_report["missions"]) -
                                      set(left_report["missions"])),
        "left": {"state_digest": a["state_digest"],
                 "ending": left_report["ending"],
                 "phase": left_report["phase"],
                 "reputation": left_report["reputation"],
                 "turns": left_report["turns"]},
        "right": {"state_digest": b["state_digest"],
                  "ending": right_report["ending"],
                  "phase": right_report["phase"],
                  "reputation": right_report["reputation"],
                  "turns": right_report["turns"]},
    }
    result = {**report, "receipt": dig(report)}
    _size(result)
    return result


def export_comparison(left: Any, right: Any) -> dict[str, Any]:
    a, b = verify_mission(left), verify_mission(right)
    report = compare_consequences(a, b)
    record = {"schema_version": BUNDLE, "left": a, "right": b,
              "report": report, "source_digest": a["source_digest"]}
    bundle = {**record, "checksum": dig(record)}
    _size(bundle)
    return bundle


def import_comparison(payload: Any) -> dict[str, Any]:
    _size(payload)
    obj = _object(payload, {"schema_version", "left", "right", "report",
                            "source_digest", "checksum"}, "mission comparison bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported mission comparison bundle")
    if type(obj["checksum"]) is not str or len(obj["checksum"]) != 64:
        raise SceneTravelError("invalid mission comparison checksum")
    if dig({k: v for k, v in obj.items() if k != "checksum"}) != obj["checksum"]:
        raise SceneTravelError("mission comparison checksum mismatch")
    a, b = verify_mission(obj["left"]), verify_mission(obj["right"])
    report = compare_consequences(a, b)
    if obj["source_digest"] != a["source_digest"] or obj["report"] != report:
        raise SceneTravelError("mission comparison replay mismatch")
    return report


def original_alternative() -> dict[str, Any]:
    actions = demo_actions()
    actions[0] = {"kind": "choose", "choice_id": "restore_lantern",
                  "option_id": "decline"}
    actions[-1] = {"kind": "finish", "ending_id": "unpledged_victory"}
    return simulate_mission(original_mission(), actions)


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-consequences")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Compare original authored alternate choices")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--session-json", required=True)
    for name in ("compare", "export"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--left-json", required=True)
        cmd.add_argument("--right-json", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            left = simulate_mission(original_mission(), demo_actions())
            result = compare_consequences(left, original_alternative())
        elif args.command == "inspect":
            result = inspect_consequences(_strict_json(args.session_json, "mission"))
        elif args.command == "import":
            result = import_comparison(_strict_json(args.bundle_json, "bundle"))
        else:
            left = _strict_json(args.left_json, "left mission")
            right = _strict_json(args.right_json, "right mission")
            result = (export_comparison(left, right) if args.command == "export"
                      else compare_consequences(left, right))
        _size(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
