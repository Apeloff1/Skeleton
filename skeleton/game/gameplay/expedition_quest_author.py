"""Typed offline quest authoring with optimistic source digests and replay preview.

The builder edits canonical quest data transactionally. It cannot execute
author-authored code, modify arbitrary files or silently migrate existing saves.
Every edit receipt is replayable from its original normalized source.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import (
    MAX_BYTES, MAX_SOURCE_BYTES, _size, normalize_quest, original_quest,
    simulate_quest, verify_quest,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _object, _parse_json,
)

SCHEMA = "skeleton.expedition_quest_edit.v1"
MAX_EDITS = 48
COLLECTIONS = {
    "location": ("locations", "id"),
    "npc": ("npcs", "id"),
    "recipe": ("recipes", "id"),
    "ending": ("endings", "id"),
}
ROOT_FIELDS = {
    "set_start": "start_location",
    "set_camp": "camp_location",
    "set_workshop": "workshop_location",
}


def _copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ))
    except (TypeError, ValueError, RecursionError) as exc:
        raise CombatSessionError("invalid quest edit JSON") from exc


def _target(source: dict[str, Any], collection: str, target_id: str) -> dict[str, Any]:
    name, key = COLLECTIONS[collection]
    found = [entry for entry in source[name] if entry[key] == target_id]
    if len(found) != 1:
        raise CombatSessionError("quest edit target missing or ambiguous")
    return found[0]


def _apply(source: dict[str, Any], raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or type(raw.get("op")) is not str:
        raise CombatSessionError("invalid quest edit operation")
    op = raw["op"]
    if op in ROOT_FIELDS:
        _object(raw, {"op", "value"}, "root edit")
        source[ROOT_FIELDS[op]] = _id(raw["value"], "root location")
        return {"op": op, "value": source[ROOT_FIELDS[op]]}
    if op == "set_expedition":
        _object(raw, {"op", "value"}, "expedition edit")
        if type(raw["value"]) is not dict:
            raise CombatSessionError("invalid expedition replacement")
        source["expedition"] = _copy(raw["value"])
        return {"op": op, "value": source["expedition"]}
    if op in ("add_location", "add_npc", "add_recipe", "add_ending"):
        _object(raw, {"op", "value"}, "add edit")
        kind = op.removeprefix("add_")
        name, key = COLLECTIONS[kind]
        value = _copy(raw["value"])
        if type(value) is not dict or key not in value:
            raise CombatSessionError("invalid added quest object")
        item_id = _id(value[key], "added object id")
        if any(entry.get(key) == item_id for entry in source[name]):
            raise CombatSessionError("quest object already exists")
        source[name].append(value)
        return {"op": op, "value": value}
    if op in ("remove_location", "remove_npc", "remove_recipe", "remove_ending"):
        _object(raw, {"op", "id"}, "remove edit")
        kind = op.removeprefix("remove_")
        name, key = COLLECTIONS[kind]
        target_id = _id(raw["id"], "removed object id")
        _target(source, kind, target_id)
        source[name] = [entry for entry in source[name] if entry[key] != target_id]
        return {"op": op, "id": target_id}
    setters = {
        "set_location_exits": ("location", "exits"),
        "set_npc_route": ("npc", "route"),
        "set_npc_gift": ("npc", "gift"),
        "set_recipe_inputs": ("recipe", "inputs"),
        "set_recipe_output": ("recipe", "output"),
        "set_ending_choices": ("ending", "choices"),
        "set_ending_items": ("ending", "items"),
        "set_ending_outcome": ("ending", "outcome"),
    }
    if op in setters:
        _object(raw, {"op", "id", "value"}, "set edit")
        kind, field = setters[op]
        target_id = _id(raw["id"], "edited object id")
        value = _copy(raw["value"])
        _target(source, kind, target_id)[field] = value
        return {"op": op, "id": target_id, "value": value}
    raise CombatSessionError("unsupported quest authoring operation")


def apply_edits(
    source: Any, operations: Any, *, expected_digest: str,
    preview_actions: Any = None,
) -> dict[str, Any]:
    """Atomically validate a batch against a versioned source digest."""
    baseline = normalize_quest(source)
    before = dig(baseline)
    if type(expected_digest) is not str or expected_digest != before:
        raise CombatSessionError("quest source optimistic digest mismatch")
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise CombatSessionError("invalid quest edit batch")
    draft = _copy(baseline)
    normalized_ops = []
    for raw in operations:
        normalized_ops.append(_apply(draft, raw))
        _size(draft, MAX_SOURCE_BYTES)
    edited = normalize_quest(draft)
    after = dig(edited)
    if after == before:
        raise CombatSessionError("quest edit batch makes no source change")
    if preview_actions is not None:
        if type(preview_actions) is not list:
            raise CombatSessionError("invalid quest preview action batch")
        preview = simulate_quest(edited, preview_actions)
    else:
        preview = None
    receipt = {
        "schema_version": SCHEMA,
        "base_source": baseline,
        "before_digest": before,
        "operations": normalized_ops,
        "operations_digest": dig(normalized_ops),
        "source": edited,
        "source_digest": after,
        "preview_actions": _copy(preview_actions),
        "preview": preview,
    }
    _size(receipt, MAX_BYTES)
    return receipt


def verify_edits(payload: Any) -> dict[str, Any]:
    """Replay the complete edit transaction and its optional gameplay preview."""
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "base_source", "before_digest",
        "operations", "operations_digest", "source", "source_digest",
        "preview_actions", "preview",
    }, "quest edit receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported quest edit receipt schema")
    rebuilt = apply_edits(
        obj["base_source"], obj["operations"],
        expected_digest=obj["before_digest"],
        preview_actions=obj["preview_actions"],
    )
    if rebuilt != obj:
        raise CombatSessionError("quest edit receipt or preview mismatch")
    return rebuilt


def save_compatibility(receipt: Any, saved: Any) -> dict[str, Any]:
    """Fail closed on source changes; never transplant a stale game state."""
    edited = verify_edits(receipt)
    old = verify_quest(saved)
    compatible = old["source_digest"] == edited["source_digest"]
    return {
        "schema_version": SCHEMA,
        "compatible": compatible,
        "old_source_digest": old["source_digest"],
        "edited_source_digest": edited["source_digest"],
        "action": "resume" if compatible else "restart_from_new_source",
    }


def original_edit_demo() -> dict[str, Any]:
    """Retune original NPC supply chain without breaking the playable quest."""
    baseline = original_quest()
    return apply_edits(
        baseline, [
            {"op": "set_npc_gift", "id": "guide", "value": "copper"},
            {"op": "set_recipe_inputs", "id": "beacon",
             "value": ["copper", "ore"]},
        ],
        expected_digest=dig(normalize_quest(baseline)),
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Edit the original NPC supply chain offline")
    edit = sub.add_parser("edit", help="Apply source-digest-fenced typed edits")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--preview-actions-json")
    verify = sub.add_parser("verify", help="Replay-check a complete edit receipt")
    verify.add_argument("--receipt-json", required=True)
    compat = sub.add_parser("compatibility", help="Check save/source continuity")
    compat.add_argument("--receipt-json", required=True)
    compat.add_argument("--session-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_edit_demo()
        elif args.command == "edit":
            result = apply_edits(
                _parse_json(args.source_json, "quest source"),
                _parse_json(args.operations_json, "quest edits"),
                expected_digest=args.expected_digest,
                preview_actions=(
                    _parse_json(args.preview_actions_json, "quest preview")
                    if args.preview_actions_json is not None else None
                ),
            )
        elif args.command == "verify":
            result = verify_edits(_parse_json(args.receipt_json, "quest edit receipt"))
        else:
            result = save_compatibility(
                _parse_json(args.receipt_json, "quest edit receipt"),
                _parse_json(args.session_json, "quest session"),
            )
        _size(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
