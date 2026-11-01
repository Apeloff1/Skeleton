"""Transactional source-bound control-point editing with gameplay preview."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_control import (
    SCHEMA as CONTROL_SCHEMA, _encoded, normalize_control,
    original_actions, original_control, play_control,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_author.v1"
MAX_EDITS = 16


def _operations(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise CombatSessionError("invalid control-point edit count")
    edits = []
    for item in raw:
        if type(item) is not dict:
            raise CombatSessionError("invalid control-point edit")
        kind = item.get("kind")
        if kind in ("set-score-target", "set-max-actions"):
            _object(item, {"kind", "value"}, "control-point scalar edit")
            limit = 200 if kind == "set-score-target" else 96
            edits.append({"kind": kind, "value": _integer(item["value"], "value", 1, limit)})
        elif kind == "set-zone-points":
            _object(item, {"kind", "zone_id", "value"}, "zone score edit")
            edits.append({
                "kind": kind, "zone_id": _id(item["zone_id"], "zone_id"),
                "value": _integer(item["value"], "value", 1, 5),
            })
        elif kind == "move-zone":
            _object(item, {"kind", "zone_id", "position"}, "zone move edit")
            pos = item["position"]
            if type(pos) is not list or len(pos) != 2:
                raise CombatSessionError("invalid zone edit position")
            edits.append({
                "kind": kind, "zone_id": _id(item["zone_id"], "zone_id"),
                "position": [
                    _integer(pos[0], "zone.x", 0, 31),
                    _integer(pos[1], "zone.y", 0, 31),
                ],
            })
        else:
            raise CombatSessionError("unsupported control-point edit")
    return edits


def author_control(source: Any, operations: Any, expected_digest: Any,
                   preview_actions: Any) -> dict[str, Any]:
    before = normalize_control(source)
    if type(expected_digest) is not str or expected_digest != dig(before):
        raise CombatSessionError("stale control-point source digest")
    edits = _operations(operations)
    if type(preview_actions) is not list or not 1 <= len(preview_actions) <= before["max_actions"]:
        raise CombatSessionError("invalid control-point preview actions")
    candidate = json.loads(_encoded(before))
    for edit in edits:
        kind = edit["kind"]
        if kind == "set-score-target":
            old = candidate["score_target"]
            candidate["score_target"] = edit["value"]
            new = edit["value"]
        elif kind == "set-max-actions":
            old = candidate["max_actions"]
            candidate["max_actions"] = edit["value"]
            new = edit["value"]
        else:
            zone = next((z for z in candidate["zones"] if z["id"] == edit["zone_id"]), None)
            if zone is None:
                raise CombatSessionError("unknown control-point zone")
            key = "points" if kind == "set-zone-points" else "position"
            old, new = zone[key], edit.get("value", edit.get("position"))
            zone[key] = new
        if old == new:
            raise CombatSessionError("control-point authoring no-op edit")
    compiled = normalize_control(candidate)
    if dig(compiled) == dig(before):
        raise CombatSessionError("control-point authoring has no net change")
    preview = play_control(compiled, preview_actions)
    result = {
        "schema_version": SCHEMA,
        "before_digest": dig(before), "after_digest": dig(compiled),
        "operations": edits, "source": compiled,
        "preview_actions": [event["action"] for event in preview["journal"]],
        "preview": preview, "claim": "offline_replay_preview_only",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_authoring(source: Any, raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "before_digest", "after_digest", "operations",
        "source", "preview_actions", "preview", "claim", "receipt",
    }, "control-point authoring receipt")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "offline_replay_preview_only":
        raise CombatSessionError("unsupported control-point authoring receipt")
    _encoded(obj)
    expected = author_control(source, obj["operations"], obj["before_digest"],
                              obj["preview_actions"])
    if expected != obj:
        raise CombatSessionError("control-point authoring receipt or preview mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Edit an original beacon game and replay preview")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source = original_control()
            result = author_control(
                source, [{"kind": "set-score-target", "value": 1}],
                dig(normalize_control(source)), original_actions()[:1],
            )
        elif args.command == "edit":
            source = _parse_json(args.source_json, "control-point source")
            result = author_control(
                source, _parse_json(args.operations_json, "control-point edits"),
                args.expected_digest, _parse_json(args.actions_json, "preview actions"),
            )
        else:
            result = verify_authoring(
                _parse_json(args.source_json, "control-point source"),
                _parse_json(args.receipt_json, "control-point authoring receipt"),
            )
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
