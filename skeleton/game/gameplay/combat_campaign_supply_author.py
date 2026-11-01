"""Transactional source-digest-fenced editor for earned offline combat supplies.

Edits are all-or-nothing; every receipt includes a replay-derived gameplay
preview. Neither content digests nor edit receipts confer authorization.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign_supply import (
    SCHEMA as SUPPLY_SCHEMA, _encoded, finish_supply, normalize_supply,
    original_supply,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_supply_author.v1"
MAX_EDITS = 12
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _operations(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise CombatSessionError("invalid supply author edit count")
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if type(item) is not dict:
            raise CombatSessionError("invalid supply author edit")
        kind = item.get("kind")
        if kind == "set-price":
            obj = _object(item, {"kind", "item", "value"}, "price edit")
            name = _id(obj["item"], "item")
            if name not in ("medkit", "ward"):
                raise CombatSessionError("unsupported supply price item")
            normalized.append({
                "kind": kind, "item": name,
                "value": _integer(obj["value"], "price", 1, 1000000),
            })
        elif kind == "set-reward":
            obj = _object(item, {"kind", "encounter_id", "value"}, "reward edit")
            normalized.append({
                "kind": kind, "encounter_id": _id(obj["encounter_id"], "encounter_id"),
                "value": _integer(obj["value"], "reward", 0, 1000000),
            })
        else:
            raise CombatSessionError("unsupported supply author edit kind")
    return normalized


def author_supply(source: Any, operations: Any,
                  expected_source_digest: Any) -> dict[str, Any]:
    before = normalize_supply(source)
    before_digest = dig(before)
    if (type(expected_source_digest) is not str
            or _DIGEST.fullmatch(expected_source_digest) is None
            or expected_source_digest != before_digest):
        raise CombatSessionError("stale or invalid supply source digest")
    edits = _operations(operations)
    candidate = copy.deepcopy(before)
    for edit in edits:
        if edit["kind"] == "set-price":
            current = candidate["prices"][edit["item"]]
            if current == edit["value"]:
                raise CombatSessionError("supply price edit is a no-op")
            candidate["prices"][edit["item"]] = edit["value"]
        else:
            entry = next(
                (e for e in candidate["campaign"]["encounters"]
                 if e["scenario"]["encounter_id"] == edit["encounter_id"]), None
            )
            if entry is None:
                raise CombatSessionError("unknown supply encounter")
            if entry["reward"] == edit["value"]:
                raise CombatSessionError("supply reward edit is a no-op")
            entry["reward"] = edit["value"]
    compiled = normalize_supply(candidate)
    after_digest = dig(compiled)
    if after_digest == before_digest:
        raise CombatSessionError("supply author transaction has no net change")
    preview = finish_supply(compiled)
    result = {
        "schema_version": SCHEMA, "source_schema": SUPPLY_SCHEMA,
        "before_digest": before_digest, "after_digest": after_digest,
        "operations": edits, "source": compiled,
        "preview_session": preview,
        "preview_state_digest": preview["state_digest"],
        "claim": "offline_replay_preview_only",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_supply_authoring(source: Any, raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source_schema", "before_digest", "after_digest",
        "operations", "source", "preview_session", "preview_state_digest",
        "claim", "receipt",
    }, "supply author receipt")
    if (obj["schema_version"] != SCHEMA
            or obj["source_schema"] != SUPPLY_SCHEMA
            or obj["claim"] != "offline_replay_preview_only"):
        raise CombatSessionError("unsupported supply author receipt")
    _encoded(obj)
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("supply author receipt digest mismatch")
    expected = author_supply(source, obj["operations"], obj["before_digest"])
    if expected != obj:
        raise CombatSessionError("supply author source or preview mismatch")
    return expected


def original_author_demo() -> dict[str, Any]:
    source = original_supply()
    return author_supply(source, [
        {"kind": "set-price", "item": "medkit", "value": 6},
        {"kind": "set-reward", "encounter_id": "reed_watch", "value": 12},
    ], dig(normalize_supply(source)))


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-supply-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Edit original prices and replay preview")
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
            result = original_author_demo()
        else:
            source = _parse_json(args.source_json, "supply source")
            if args.command == "edit":
                result = author_supply(
                    source, _parse_json(args.operations_json, "supply edits"),
                    args.expected_digest,
                )
            else:
                result = verify_supply_authoring(
                    source, _parse_json(args.receipt_json, "supply author receipt"),
                )
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError, OverflowError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
