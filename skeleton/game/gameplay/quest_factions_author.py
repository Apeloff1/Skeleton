"""Transactional authoring of replayed faction policies and NPC consequences."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import demo_actions
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.quest_factions import (
    MAX_BYTES, MAX_SOURCE_BYTES, SCHEMA as SOURCE_SCHEMA, _bounded,
    normalize_factions, original_factions, simulate_factions, verify_factions,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _object, _parse_json,
)

SCHEMA = "skeleton.quest_factions_author.v1"
MAX_EDITS = 32


def _copy(value: Any) -> Any:
    _bounded(value, MAX_BYTES)
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _faction(source: dict[str, Any], faction_id: str) -> dict[str, Any]:
    found = [f for f in source["factions"] if f["id"] == faction_id]
    if len(found) != 1:
        raise CombatSessionError("faction edit target missing or ambiguous")
    return found[0]


def _apply(source: dict[str, Any], raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or type(raw.get("op")) is not str:
        raise CombatSessionError("invalid faction edit")
    op = raw["op"]
    if op == "add_faction":
        _object(raw, {"op", "value"}, "add faction")
        value = _copy(raw["value"])
        if type(value) is not dict or "id" not in value:
            raise CombatSessionError("invalid added faction")
        faction_id = _id(value["id"], "faction_id")
        if any(f["id"] == faction_id for f in source["factions"]):
            raise CombatSessionError("faction already exists")
        source["factions"].append(value)
        return {"op": op, "value": value}
    if op == "remove_faction":
        _object(raw, {"op", "id"}, "remove faction")
        faction_id = _id(raw["id"], "faction_id")
        _faction(source, faction_id)
        source["factions"] = [
            f for f in source["factions"] if f["id"] != faction_id
        ]
        return {"op": op, "id": faction_id}
    if op in ("set_members", "set_aid_delta", "set_decline_delta"):
        _object(raw, {"op", "id", "value"}, "edit faction")
        faction_id = _id(raw["id"], "faction_id")
        field = {
            "set_members": "members",
            "set_aid_delta": "aid_delta",
            "set_decline_delta": "decline_delta",
        }[op]
        value = _copy(raw["value"])
        _faction(source, faction_id)[field] = value
        return {"op": op, "id": faction_id, "value": value}
    if op == "set_ending_requirements":
        _object(raw, {"op", "value"}, "edit ending requirements")
        value = _copy(raw["value"])
        source["ending_requirements"] = value
        return {"op": op, "value": value}
    if op == "set_quest_source":
        _object(raw, {"op", "value"}, "edit underlying quest")
        value = _copy(raw["value"])
        source["quest"] = value
        return {"op": op, "value": value}
    raise CombatSessionError("unsupported faction authoring operation")


def apply_edits(source: Any, operations: Any, *, expected_digest: str,
                preview_actions: Any = None) -> dict[str, Any]:
    """All-or-nothing source edit; stale digests never commit."""
    baseline = normalize_factions(source)
    before = dig(baseline)
    if type(expected_digest) is not str or expected_digest != before:
        raise CombatSessionError("faction source optimistic digest mismatch")
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise CombatSessionError("invalid faction edit batch")
    draft = _copy(baseline)
    normalized_ops = []
    for raw in operations:
        normalized_ops.append(_apply(draft, raw))
        _bounded(draft, MAX_SOURCE_BYTES)
    edited = normalize_factions(draft)
    after = dig(edited)
    if before == after:
        raise CombatSessionError("faction edit batch makes no source change")
    if preview_actions is not None:
        if type(preview_actions) is not list:
            raise CombatSessionError("invalid faction preview actions")
        preview = simulate_factions(edited, preview_actions)
    else:
        preview = None
    receipt = {
        "schema_version": SCHEMA, "base_source": baseline,
        "before_digest": before, "operations": normalized_ops,
        "operations_digest": dig(normalized_ops),
        "source": edited, "source_digest": after,
        "preview_actions": _copy(preview_actions), "preview": preview,
    }
    _bounded(receipt, MAX_BYTES)
    return receipt


def verify_edits(raw: Any) -> dict[str, Any]:
    _bounded(raw, MAX_BYTES)
    obj = _object(raw, {
        "schema_version", "base_source", "before_digest",
        "operations", "operations_digest", "source", "source_digest",
        "preview_actions", "preview",
    }, "faction edit receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported faction edit receipt")
    rebuilt = apply_edits(
        obj["base_source"], obj["operations"],
        expected_digest=obj["before_digest"],
        preview_actions=obj["preview_actions"],
    )
    if rebuilt != obj:
        raise CombatSessionError("faction edit receipt or preview mismatch")
    return rebuilt


def save_compatibility(receipt: Any, saved: Any) -> dict[str, Any]:
    edited = verify_edits(receipt)
    session = verify_factions(saved)
    compatible = session["source_digest"] == edited["source_digest"]
    return {
        "schema_version": "skeleton.quest_factions_save_compatibility.v1",
        "compatible": compatible,
        "old_source_digest": session["source_digest"],
        "new_source_digest": edited["source_digest"],
        "action": "resume" if compatible else "restart_from_new_source",
    }


def original_edit_demo() -> dict[str, Any]:
    source = original_factions()
    return apply_edits(
        source, [{"op": "set_aid_delta", "id": "harbor_wardens", "value": 3}],
        expected_digest=dig(normalize_factions(source)),
        preview_actions=demo_actions(),
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-factions-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--preview-actions-json")
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    compat = sub.add_parser("compatibility")
    compat.add_argument("--receipt-json", required=True)
    compat.add_argument("--session-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_edit_demo()
        elif args.command == "edit":
            result = apply_edits(
                _parse_json(args.source_json, "faction source"),
                _parse_json(args.operations_json, "faction operations"),
                expected_digest=args.expected_digest,
                preview_actions=(
                    _parse_json(args.preview_actions_json, "faction preview")
                    if args.preview_actions_json is not None else None
                ),
            )
        elif args.command == "verify":
            result = verify_edits(_parse_json(args.receipt_json, "edit receipt"))
        else:
            result = save_compatibility(
                _parse_json(args.receipt_json, "edit receipt"),
                _parse_json(args.session_json, "faction session"),
            )
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
            raise CombatSessionError("faction author CLI output exceeds size budget")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
