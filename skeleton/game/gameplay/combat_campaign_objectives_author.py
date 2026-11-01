"""Transactional objective editing with source leases and canonical playable preview.

The authoring receipt is reproducible evidence, not an authorization token.
All operations are bounded data, never Python source or executable callbacks.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign_objectives import (
    MAX_OBJECTIVES, _encoded, finish_objectives, normalize_objectives,
    objective_summary, original_objectives, package_objectives,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _object, _parse_json,
)

SCHEMA = "skeleton.combat_objectives_author.v1"
MAX_EDITS = 16
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EDIT_KINDS = frozenset({
    "add-objective", "remove-objective", "set-points", "set-threshold",
    "set-kind", "set-requires",
})


def _validate_edits(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise CombatSessionError("invalid objectives edit count")
    result: list[dict[str, Any]] = []
    for entry in raw:
        if type(entry) is not dict:
            raise CombatSessionError("invalid objectives edit")
        kind = entry.get("kind")
        if type(kind) is not str or kind not in EDIT_KINDS:
            raise CombatSessionError("unsupported objectives edit kind")
        if kind == "add-objective":
            checked = _object(entry, {"kind", "objective"}, "objective add")
            if type(checked["objective"]) is not dict:
                raise CombatSessionError("invalid new objective")
            result.append({"kind": kind, "objective": checked["objective"]})
        elif kind == "remove-objective":
            checked = _object(entry, {"kind", "objective_id"}, "objective removal")
            result.append({
                "kind": kind, "objective_id": _id(checked["objective_id"], "objective_id"),
            })
        else:
            checked = _object(entry, {"kind", "objective_id", "value"}, "objective edit")
            objective_id = _id(checked["objective_id"], "objective_id")
            result.append({"kind": kind, "objective_id": objective_id,
                           "value": checked["value"]})
    _encoded(result)
    return result


def author_objectives(source: Any, operations: Any,
                      expected_source_digest: Any) -> dict[str, Any]:
    before = normalize_objectives(source)
    source_digest = dig(before)
    if (type(expected_source_digest) is not str
            or SHA256.fullmatch(expected_source_digest) is None
            or expected_source_digest != source_digest):
        raise CombatSessionError("stale or invalid objectives source digest")
    edits = _validate_edits(operations)
    candidate = json.loads(_encoded(before))
    for edit in edits:
        kind = edit["kind"]
        if kind == "add-objective":
            if len(candidate["objectives"]) >= MAX_OBJECTIVES:
                raise CombatSessionError("objectives authoring capacity exceeded")
            candidate["objectives"].append(edit["objective"])
            continue
        index = next(
            (i for i, obj in enumerate(candidate["objectives"])
             if obj["objective_id"] == edit["objective_id"]), None
        )
        if index is None:
            raise CombatSessionError("unknown authored objective")
        if kind == "remove-objective":
            candidate["objectives"].pop(index)
            continue
        key = {
            "set-points": "points", "set-threshold": "threshold",
            "set-kind": "kind", "set-requires": "requires",
        }[kind]
        if candidate["objectives"][index][key] == edit["value"]:
            raise CombatSessionError("objectives authoring no-op edit")
        candidate["objectives"][index][key] = edit["value"]
    compiled = normalize_objectives(candidate)
    if dig(compiled) == source_digest:
        raise CombatSessionError("objectives transaction has no net change")
    played = finish_objectives(compiled)
    portable = package_objectives(played)
    result = {
        "schema_version": SCHEMA,
        "before_digest": source_digest, "after_digest": dig(compiled),
        "operations": edits, "source": compiled,
        "preview_summary": objective_summary(played),
        "preview_package": portable,
        "claim": "offline_replay_preview_only",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_objectives_authoring(source: Any, raw: Any) -> dict[str, Any]:
    receipt = _object(raw, {
        "schema_version", "before_digest", "after_digest", "operations",
        "source", "preview_summary", "preview_package", "claim", "receipt",
    }, "objectives authoring receipt")
    if (receipt["schema_version"] != SCHEMA
            or receipt["claim"] != "offline_replay_preview_only"):
        raise CombatSessionError("unsupported objectives authoring receipt")
    _encoded(receipt)
    if receipt["receipt"] != dig({k: v for k, v in receipt.items() if k != "receipt"}):
        raise CombatSessionError("objectives authoring receipt digest mismatch")
    expected = author_objectives(source, receipt["operations"], receipt["before_digest"])
    if expected != receipt:
        raise CombatSessionError("objectives authoring replay mismatch")
    return expected


def original_authoring_demo() -> dict[str, Any]:
    source = original_objectives()
    return author_objectives(source, [
        {"kind": "set-points", "objective_id": "guard_lantern", "value": 25},
    ], dig(normalize_objectives(source)))


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-objectives-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Edit original objectives and preview playable export")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_authoring_demo()
        else:
            source = _parse_json(args.source_json, "objectives source")
            if args.command == "edit":
                result = author_objectives(
                    source, _parse_json(args.operations_json, "objective edits"),
                    args.expected_digest,
                )
            else:
                result = verify_objectives_authoring(
                    source, _parse_json(args.receipt_json, "objectives receipt"),
                )
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
