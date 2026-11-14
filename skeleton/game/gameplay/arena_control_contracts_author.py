"""Transactional capture-contract editing with canonical playable previews."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_control import _encoded, original_actions
from skeleton.game.gameplay.arena_control_contracts import (
    normalize_contract, original_contract, play_contract, verify_contract,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_contracts_author.v1"
MAX_EDITS = 16


def author_contract(source: Any, operations: Any, expected_digest: Any,
                    preview_actions: Any) -> dict[str, Any]:
    before = normalize_contract(source)
    if type(expected_digest) is not str or expected_digest != dig(before):
        raise CombatSessionError("stale capture contract source digest")
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise CombatSessionError("invalid capture contract edit count")
    if type(preview_actions) is not list:
        raise CombatSessionError("invalid capture contract preview actions")
    candidate = json.loads(_encoded(before))
    normalized = []
    for raw in operations:
        item = _object(raw, {"kind", "objective_id", "value"},
                       "capture contract edit")
        kind = item["kind"]
        objective_id = _id(item["objective_id"], "objective_id")
        target = next((entry for entry in candidate["objectives"]
                       if entry["id"] == objective_id), None)
        if target is None:
            raise CombatSessionError("unknown capture contract objective")
        if kind == "set-reward":
            value = _integer(item["value"], "reward", 0, 100000)
            key = "reward"
        elif kind == "set-target":
            value = item["value"]
            key = "target"
        else:
            raise CombatSessionError("unsupported capture contract edit")
        if target[key] == value:
            raise CombatSessionError("capture contract authoring no-op edit")
        target[key] = value
        normalized.append({"kind": kind, "objective_id": objective_id,
                           "value": value})
    after = normalize_contract(candidate)
    if dig(after) == dig(before):
        raise CombatSessionError("capture contract authoring produced no changes")
    preview = play_contract(after, preview_actions)
    verify_contract(preview)
    result = {"schema_version": SCHEMA, "before_digest": dig(before),
              "after_digest": dig(after), "source": after,
              "operations": normalized, "preview_actions": preview_actions,
              "preview": preview, "preview_digest": dig(preview)}
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_author_receipt(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "before_digest", "after_digest",
                        "source", "operations", "preview_actions", "preview",
                        "preview_digest", "receipt"}, "contract author receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported capture contract author receipt")
    _encoded(obj)
    after = normalize_contract(obj["source"])
    if dig(after) != obj["after_digest"]:
        raise CombatSessionError("capture contract authored source mismatch")
    preview = play_contract(after, obj["preview_actions"])
    if preview != obj["preview"] or dig(preview) != obj["preview_digest"]:
        raise CombatSessionError("capture contract author preview mismatch")
    if dig({k: v for k, v in obj.items() if k != "receipt"}) != obj["receipt"]:
        raise CombatSessionError("capture contract author receipt mismatch")
    # A receipt proves the after-source preview, not that a historical
    # before-source existed. No provenance or signature claim is made.
    return obj


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-contracts-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Edit and preview an original capture bounty")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--preview-actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source = original_contract()
            result = author_contract(source, [
                {"kind": "set-reward", "objective_id": "secure_west", "value": 17},
            ], dig(normalize_contract(source)), original_actions())
        elif args.command == "edit":
            result = author_contract(
                _parse_json(args.source_json, "contract source"),
                _parse_json(args.operations_json, "contract edits"),
                args.expected_digest,
                _parse_json(args.preview_actions_json, "contract preview actions"))
        else:
            result = verify_author_receipt(_parse_json(args.receipt_json, "contract author receipt"))
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
