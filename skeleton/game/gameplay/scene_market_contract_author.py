"""Transactional, source-digest-fenced editing for authored market commissions."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _bounded, _json
from skeleton.game.gameplay.scene_market_contract import (
    normalize_contract_source, original_contract,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_market_contract_edit.v1"
MAX_EDITS = 32


def edit_contract(source: Any, operations: Any, expected_digest: str) -> dict[str, Any]:
    before = normalize_contract_source(source)
    if type(expected_digest) is not str or expected_digest != dig(before):
        raise SceneTravelError("contract author source changed since read")
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise SceneTravelError("invalid contract author batch")
    after = copy.deepcopy(before)
    normalized = []
    for raw in operations:
        if type(raw) is not dict:
            raise SceneTravelError("invalid contract author operation")
        kind = raw.get("kind")
        if kind == "set_required":
            item = _object(raw, {"kind", "contract_ids"}, "contract author operation")
            ids = item["contract_ids"]
            if type(ids) is not list or not 1 <= len(ids) <= MAX_EDITS:
                raise SceneTravelError("invalid required contracts")
            normalized_ids = sorted(_id(value, "required contract") for value in ids)
            after["required_contracts"] = normalized_ids
            normalized.append({"kind": kind, "contract_ids": normalized_ids})
        elif kind in ("set_deadline", "set_min_reputation", "set_reward_score"):
            item = _object(raw, {"kind", "contract_id", "value"}, "contract author operation")
            ident = _id(item["contract_id"], "contract id")
            target = next(
                (entry for entry in after["contracts"] if entry["contract_id"] == ident),
                None,
            )
            if target is None:
                raise SceneTravelError("contract author references unknown contract")
            field, low, high = {
                "set_deadline": ("deadline_tick", 1, 256),
                "set_min_reputation": ("min_reputation", 0, 3200),
                "set_reward_score": ("reward_score", 1, 1000),
            }[kind]
            value = _limit(item["value"], field, low, high)
            target[field] = value
            normalized.append({"kind": kind, "contract_id": ident, "value": value})
        else:
            raise SceneTravelError("unsupported contract author operation")
    after = normalize_contract_source(after)
    if after == before:
        raise SceneTravelError("contract author batch has no changes")
    receipt = {
        "schema_version": SCHEMA, "before": before, "after": after,
        "before_digest": dig(before), "after_digest": dig(after),
        "operations": normalized,
    }
    receipt["checksum"] = dig(receipt)
    _bounded(receipt)
    return receipt


def verify_contract_edit(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "before", "after", "before_digest",
        "after_digest", "operations", "checksum",
    }, "contract author receipt")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported contract author receipt")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("contract author checksum mismatch")
    rebuilt = edit_contract(obj["before"], obj["operations"], obj["before_digest"])
    if rebuilt != obj:
        raise SceneTravelError("contract author replay or source mismatch")
    return rebuilt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-contract-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    sub.add_parser("verify").add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_contract()
            result = edit_contract(source, [{
                "kind": "set_reward_score", "contract_id": "sanctuary_commission",
                "value": 26,
            }], dig(normalize_contract_source(source)))
        elif args.command == "edit":
            result = edit_contract(
                _json(args.source_json), _json(args.operations_json),
                args.expected_digest,
            )
        else:
            result = verify_contract_edit(_json(args.receipt_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
