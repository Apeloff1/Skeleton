"""Transactional source-fenced NPC rescue authoring with real mission preview."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _id, _json, _limit, _object,
)
from skeleton.game.gameplay.scene_weather import _export
from skeleton.game.gameplay.scene_weather_rescue import (
    normalize_rescue, original_rescue, play_rescue,
)

SCHEMA = "skeleton.weather_rescue_author.v1"
MAX_EDITS = 16


def _edits(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise SceneTravelError("invalid rescue authoring edit count")
    edits = []
    for raw_edit in raw:
        edit = _object(raw_edit, {"npc_id", "field", "value"}, "rescue edit")
        npc_id = _id(edit["npc_id"], "npc_id")
        field = edit["field"]
        if field not in ("deadline", "max_storm_exposure", "reward",
                         "origin_scene", "shelter_scene") or type(field) is not str:
            raise SceneTravelError("unsupported rescue authoring field")
        value = edit["value"]
        if field == "deadline":
            value = _limit(value, field, 1, 256)
        elif field == "max_storm_exposure":
            value = _limit(value, field, 0, 8)
        elif field == "reward":
            value = _limit(value, field, 1, 10000)
        else:
            value = _id(value, field)
        edits.append({"npc_id": npc_id, "field": field, "value": value})
    return edits


def author_rescue(source: Any, operations: Any, expected_digest: Any,
                  preview_actions: Any) -> dict[str, Any]:
    before = normalize_rescue(source)
    before_digest = dig(before)
    if type(expected_digest) is not str or expected_digest != before_digest:
        raise SceneTravelError("stale rescue source digest")
    edits = _edits(operations)
    if type(preview_actions) is not list or not 1 <= len(preview_actions) <= before["weather"]["world"]["step_limit"]:
        raise SceneTravelError("invalid rescue preview actions")
    candidate = json.loads(_export(before))
    for edit in edits:
        npc = next((n for n in candidate["npcs"] if n["npc_id"] == edit["npc_id"]), None)
        if npc is None:
            raise SceneTravelError("unknown rescue authoring NPC")
        if npc[edit["field"]] == edit["value"]:
            raise SceneTravelError("rescue authoring no-op edit")
        npc[edit["field"]] = edit["value"]
    compiled = normalize_rescue(candidate)
    if dig(compiled) == before_digest:
        raise SceneTravelError("rescue authoring has no net change")
    preview = play_rescue(compiled, preview_actions)
    result = {
        "schema_version": SCHEMA, "before_digest": before_digest,
        "after_digest": dig(compiled), "operations": edits,
        "source": compiled,
        "preview_actions": [
            event["action"] for event in preview["state"]["journal"]
        ],
        "preview": preview, "claim": "offline_replay_preview_only",
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def verify_authoring(source: Any, raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "before_digest", "after_digest", "operations",
        "source", "preview_actions", "preview", "claim", "receipt",
    }, "rescue authoring receipt")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "offline_replay_preview_only":
        raise SceneTravelError("unsupported rescue authoring receipt")
    _export(obj)
    expected = author_rescue(
        source, obj["operations"], obj["before_digest"], obj["preview_actions"],
    )
    if expected != obj:
        raise SceneTravelError("rescue authoring source or preview mismatch")
    return expected


def original_authoring_demo() -> dict[str, Any]:
    source, actions = original_rescue()
    return author_rescue(
        source, [{"npc_id": "canal_medic", "field": "reward", "value": 30}],
        dig(normalize_rescue(source)), actions,
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-rescue-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Edit and preview original NPC rescue mission")
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
            result = original_authoring_demo()
        elif args.command == "edit":
            result = author_rescue(
                _json(args.source_json, "rescue source"),
                _json(args.operations_json, "rescue edits"),
                args.expected_digest, _json(args.actions_json, "rescue preview actions"),
            )
        else:
            result = verify_authoring(
                _json(args.source_json, "rescue source"),
                _json(args.receipt_json, "rescue authoring receipt"),
            )
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
