"""Transactional, source-digest-fenced editor for original market quests.

All edits are inert data, applied to a private normalized copy, and validated
as a whole. A receipt can be independently replayed to prove the edited
source and its optional playable preview, without trusting editor claims.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _json, normalize_market, original_market, simulate_market,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_market_edit.v1"
MAX_EDITS = 64


def _operation(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("market edit must be an object")
    kind = raw.get("kind")
    if kind not in (
        "set_price", "set_stock", "set_coin",
        "set_recipe_input", "set_delivery_reputation",
    ):
        raise SceneTravelError("unsupported market edit")
    if kind == "set_coin":
        obj = _object(raw, {"kind", "pickup", "value"}, "coin edit")
        return {"kind": kind, "pickup": _id(obj["pickup"], "pickup"),
                "value": _limit(obj["value"], "coin amount", 1, 100)}
    if kind == "set_recipe_input":
        obj = _object(raw, {"kind", "recipe_id", "item_id", "value"},
                      "recipe edit")
        return {
            "kind": kind, "recipe_id": _id(obj["recipe_id"], "recipe"),
            "item_id": _id(obj["item_id"], "ingredient"),
            "value": _limit(obj["value"], "ingredient quantity", 1, 32),
        }
    field = "offer_id" if kind in ("set_price", "set_stock") else "delivery_id"
    obj = _object(raw, {"kind", field, "value"}, "market edit")
    upper = 1000 if kind == "set_price" else 32 if kind == "set_stock" else 100
    return {"kind": kind, field: _id(obj[field], field),
            "value": _limit(obj["value"], "edit value", 1, upper)}


def _apply(source: dict[str, Any], op: dict[str, Any]) -> None:
    kind = op["kind"]
    target = None
    if kind == "set_coin":
        target = next((c for c in source["coin_pickups"]
                       if c["pickup"] == op["pickup"]), None)
        field = "amount"
    elif kind in ("set_price", "set_stock"):
        target = next((o for market in source["markets"]
                       for o in market["offers"]
                       if o["offer_id"] == op["offer_id"]), None)
        field = "price" if kind == "set_price" else "stock"
    elif kind == "set_recipe_input":
        recipe = next((r for r in source["recipes"]
                       if r["recipe_id"] == op["recipe_id"]), None)
        if recipe is None or op["item_id"] not in recipe["inputs"]:
            raise SceneTravelError("recipe ingredient not authored")
        recipe["inputs"][op["item_id"]] = op["value"]
        return
    else:
        target = next((d for d in source["deliveries"]
                       if d["delivery_id"] == op["delivery_id"]), None)
        field = "reputation"
    if target is None:
        raise SceneTravelError("market edit target not authored")
    target[field] = op["value"]


def edit_market(source: Any, operations: Any, expected_source_digest: str,
                preview_actions: Any = None) -> dict[str, Any]:
    original = normalize_market(source)
    before = dig(original)
    if (type(expected_source_digest) is not str
            or expected_source_digest != before):
        raise SceneTravelError("market source changed since editor read")
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise SceneTravelError("invalid market edit batch")
    cleaned = [_operation(op) for op in operations]
    changed = copy.deepcopy(original)
    for op in cleaned:
        _apply(changed, op)
    updated = normalize_market(changed)
    if updated == original:
        raise SceneTravelError("market edit has no effect")
    if preview_actions is not None and type(preview_actions) is not list:
        raise SceneTravelError("invalid market preview actions")
    preview = (
        simulate_market(updated, preview_actions)
        if preview_actions is not None else None
    )
    receipt = {
        "schema_version": SCHEMA, "original_source": original,
        "expected_source_digest": before, "operations": cleaned,
        "source": updated, "source_digest": dig(updated),
        "preview_actions": preview_actions,
        "preview_state_digest": (
            preview["state_digest"] if preview is not None else None
        ),
        "preview_phase": (
            preview["state"]["phase"] if preview is not None else None
        ),
    }
    receipt["checksum"] = dig(receipt)
    _bounded(receipt)
    return receipt


def verify_market_edit(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    receipt = _object(raw, {
        "schema_version", "original_source", "expected_source_digest",
        "operations", "source", "source_digest", "preview_actions",
        "preview_state_digest", "preview_phase", "checksum",
    }, "market edit receipt")
    if receipt["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported market edit receipt")
    replay = edit_market(
        receipt["original_source"], receipt["operations"],
        receipt["expected_source_digest"], receipt["preview_actions"],
    )
    if replay != receipt:
        raise SceneTravelError("market edit receipt or preview mismatch")
    return replay


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--expected-source-digest", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--preview-actions-json")
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_market()
            result = edit_market(
                source, [{"kind": "set_price", "offer_id": "copper_badge",
                          "value": 3}],
                dig(normalize_market(source)), actions,
            )
        elif args.command == "edit":
            result = edit_market(
                _json(args.source_json), _json(args.operations_json),
                args.expected_source_digest,
                _json(args.preview_actions_json)
                if args.preview_actions_json is not None else None,
            )
        else:
            result = verify_market_edit(_json(args.receipt_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
