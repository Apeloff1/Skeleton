"""Transactional authoring of original weather cycles and collision gates.

All edits are validated against the canonical scene graph before publication.
Preview routes use the real weather and scene runtime; a budget-limited result
is never presented as a proved victory. Source digests are not signatures.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _json, _object
from skeleton.game.gameplay.scene_weather import (
    _export, normalize_weather, original_weather_demo,
)
from skeleton.game.gameplay.scene_weather_solver import plan_weather

SCHEMA = "skeleton.scene_weather_author.v1"
MAX_EDITS = 16


def _validated_edit(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid weather authoring operation")
    kind = raw.get("kind")
    if kind == "set-cycle":
        _object(raw, {"kind", "conditions"}, "weather cycle edit")
        conditions = raw["conditions"]
        if type(conditions) is not list:
            raise SceneTravelError("invalid authored weather cycle")
        return {"kind": kind, "conditions": list(conditions)}
    if kind == "set-gate":
        _object(raw, {"kind", "scene_id", "exit_id", "conditions"},
                "weather gate edit")
        conditions = raw["conditions"]
        if type(conditions) is not list:
            raise SceneTravelError("invalid authored gate conditions")
        return {
            "kind": kind,
            "scene_id": _id(raw["scene_id"], "scene_id"),
            "exit_id": _id(raw["exit_id"], "exit_id"),
            "conditions": list(conditions),
        }
    if kind == "remove-gate":
        _object(raw, {"kind", "scene_id", "exit_id"}, "weather gate removal")
        return {
            "kind": kind,
            "scene_id": _id(raw["scene_id"], "scene_id"),
            "exit_id": _id(raw["exit_id"], "exit_id"),
        }
    raise SceneTravelError("unsupported weather authoring operation")


def edit_weather(
    source: Any, operations: Any, expected_source_digest: Any,
    *, max_states: int = 256, max_depth: int = 32,
) -> dict[str, Any]:
    """Atomically edit gates/cycle, compile, play and return a replay receipt."""
    before = normalize_weather(source)
    before_digest = dig(before)
    if (type(expected_source_digest) is not str
            or expected_source_digest != before_digest):
        raise SceneTravelError("stale weather authoring source digest")
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise SceneTravelError("invalid weather edit count")
    candidate = json.loads(_export(before))
    edits: list[dict[str, Any]] = []
    for raw in operations:
        edit = _validated_edit(raw)
        if edit["kind"] == "set-cycle":
            if candidate["cycle"] == edit["conditions"]:
                raise SceneTravelError("no-op weather cycle edit")
            candidate["cycle"] = edit["conditions"]
        else:
            rules = candidate["blocked_exits"]
            found = next((
                i for i, gate in enumerate(rules)
                if gate["scene_id"] == edit["scene_id"]
                and gate["exit_id"] == edit["exit_id"]
            ), None)
            if edit["kind"] == "remove-gate":
                if found is None:
                    raise SceneTravelError("unknown authored weather gate")
                del rules[found]
            else:
                gate = {
                    "scene_id": edit["scene_id"], "exit_id": edit["exit_id"],
                    "conditions": edit["conditions"],
                }
                if found is None:
                    rules.append(gate)
                elif rules[found] == gate:
                    raise SceneTravelError("no-op weather gate edit")
                else:
                    rules[found] = gate
        edits.append(edit)
    compiled = normalize_weather(candidate)
    after_digest = dig(compiled)
    if after_digest == before_digest:
        raise SceneTravelError("weather authoring transaction has no net change")
    preview = plan_weather(compiled, max_states=max_states, max_depth=max_depth)
    result = {
        "schema_version": SCHEMA, "before_digest": before_digest,
        "after_digest": after_digest, "operations": edits,
        "source": compiled, "preview": preview,
        "max_states": max_states, "max_depth": max_depth,
        "claim": "offline_replay_preview_only",
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def verify_edit(source: Any, raw: Any) -> dict[str, Any]:
    """Recompile and replay the full transaction against the original source."""
    report = _object(raw, {
        "schema_version", "before_digest", "after_digest", "operations",
        "source", "preview", "max_states", "max_depth", "claim", "receipt",
    }, "weather authoring receipt")
    if (report["schema_version"] != SCHEMA
            or report["claim"] != "offline_replay_preview_only"):
        raise SceneTravelError("unsupported weather authoring receipt")
    _export(report)
    expected = edit_weather(
        source, report["operations"], report["before_digest"],
        max_states=report["max_states"], max_depth=report["max_depth"],
    )
    if expected != report:
        raise SceneTravelError("weather authoring or preview replay mismatch")
    return expected


def original_authoring_demo() -> dict[str, Any]:
    source, _ = original_weather_demo()
    return edit_weather(source, [{
        "kind": "set-cycle", "conditions": ["storm", "storm", "clear"],
    }], dig(normalize_weather(source)))


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--max-states", type=int, default=256)
    edit.add_argument("--max-depth", type=int, default=32)
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_authoring_demo()
        elif args.command == "edit":
            result = edit_weather(
                _json(args.source_json, "weather source"),
                _json(args.operations_json, "weather edits"),
                args.expected_digest,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            result = verify_edit(
                _json(args.source_json, "weather source"),
                _json(args.receipt_json, "weather edit receipt"),
            )
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
