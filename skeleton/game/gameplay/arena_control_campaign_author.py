"""Atomic multi-stage control campaign editing with full playable preview.

Nested arena-control edits reuse the canonical editor and are committed only
after all stages and their actual combat/capture replays validate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_control import _encoded, original_actions
from skeleton.game.gameplay.arena_control_author import author_control
from skeleton.game.gameplay.arena_control_campaign import (
    normalize_campaign, original_campaign, play_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_campaign_author.v1"
MAX_EDITS = 16


def _edits(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise CombatSessionError("invalid control campaign edit count")
    result: list[dict[str, Any]] = []
    for item in raw:
        if type(item) is not dict:
            raise CombatSessionError("invalid control campaign edit")
        kind = item.get("kind")
        if kind == "set-stage-reward":
            _object(item, {"kind", "control_id", "value"}, "campaign reward edit")
            result.append({
                "kind": kind, "control_id": _id(item["control_id"], "control_id"),
                "value": _integer(item["value"], "reward", 0, 100000),
            })
        elif kind == "set-required-wins":
            _object(item, {"kind", "value"}, "campaign wins edit")
            result.append({
                "kind": kind, "value": _integer(item["value"], "required_wins", 1, 4),
            })
        elif kind == "edit-stage-control":
            _object(item, {
                "kind", "control_id", "operations", "preview_actions",
            }, "campaign nested control edit")
            if type(item["operations"]) is not list or type(item["preview_actions"]) is not list:
                raise CombatSessionError("invalid nested control edit lists")
            result.append({
                "kind": kind, "control_id": _id(item["control_id"], "control_id"),
                "operations": item["operations"],
                "preview_actions": item["preview_actions"],
            })
        else:
            raise CombatSessionError("unsupported control campaign edit")
    return result


def author_campaign(source: Any, operations: Any, expected_digest: Any,
                    preview_rounds: Any) -> dict[str, Any]:
    before = normalize_campaign(source)
    before_digest = dig(before)
    if type(expected_digest) is not str or expected_digest != before_digest:
        raise CombatSessionError("stale control campaign source digest")
    edits = _edits(operations)
    if type(preview_rounds) is not list or len(preview_rounds) != len(before["stages"]):
        raise CombatSessionError("control campaign preview must cover all stages")
    candidate = json.loads(_encoded(before))
    child_receipts: list[dict[str, Any]] = []
    normalized_edits: list[dict[str, Any]] = []
    for edit in edits:
        kind = edit["kind"]
        if kind == "set-required-wins":
            previous = candidate["required_wins"]
            candidate["required_wins"] = edit["value"]
            if previous == edit["value"]:
                raise CombatSessionError("control campaign authoring no-op edit")
            normalized_edits.append(edit)
            continue
        stage = next((
            entry for entry in candidate["stages"]
            if entry["control"]["control_id"] == edit["control_id"]
        ), None)
        if stage is None:
            raise CombatSessionError("unknown control campaign stage")
        if kind == "set-stage-reward":
            previous = stage["reward"]
            stage["reward"] = edit["value"]
            if previous == edit["value"]:
                raise CombatSessionError("control campaign authoring no-op edit")
            normalized_edits.append(edit)
        else:
            child = author_control(
                stage["control"], edit["operations"],
                dig(stage["control"]), edit["preview_actions"],
            )
            stage["control"] = child["source"]
            child_receipts.append(child)
            normalized_edits.append({
                "kind": kind, "control_id": edit["control_id"],
                "operations": child["operations"],
                "preview_actions": child["preview_actions"],
            })
    compiled = normalize_campaign(candidate)
    if dig(compiled) == before_digest:
        raise CombatSessionError("control campaign authoring has no net change")
    preview = play_campaign(compiled, preview_rounds)
    if preview["state"]["phase"] == "active":
        raise CombatSessionError("control campaign authoring preview incomplete")
    result = {
        "schema_version": SCHEMA, "before_digest": before_digest,
        "after_digest": dig(compiled), "operations": normalized_edits,
        "source": compiled,
        "preview_rounds": [entry["actions"] for entry in preview["journal"]],
        "preview": preview, "child_receipts": child_receipts,
        "claim": "offline_replay_preview_only",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_authoring(source: Any, raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "before_digest", "after_digest", "operations",
        "source", "preview_rounds", "preview", "child_receipts",
        "claim", "receipt",
    }, "control campaign authoring receipt")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "offline_replay_preview_only":
        raise CombatSessionError("unsupported control campaign authoring receipt")
    _encoded(obj)
    expected = author_campaign(
        source, obj["operations"], obj["before_digest"], obj["preview_rounds"],
    )
    if expected != obj:
        raise CombatSessionError("control campaign authoring receipt mismatch")
    return expected


def original_authoring_demo() -> dict[str, Any]:
    source = original_campaign()
    return author_campaign(
        source, [
            {"kind": "set-stage-reward", "control_id": "lantern_canal_control", "value": 12},
            {"kind": "set-required-wins", "value": 1},
        ],
        dig(normalize_campaign(source)),
        [original_actions(), original_actions()],
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-campaign-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Transactionally edit original beacon campaign")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--rounds-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_authoring_demo()
        elif args.command == "edit":
            result = author_campaign(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.operations_json, "campaign edits"),
                args.expected_digest,
                _parse_json(args.rounds_json, "campaign preview rounds"),
            )
        else:
            result = verify_authoring(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.receipt_json, "campaign authoring receipt"),
            )
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
