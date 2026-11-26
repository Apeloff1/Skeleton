"""Transactional weather-market authoring with source-fenced playable previews.

Edits cannot rewrite delivery rewards, grant inventory, or bypass the
canonical weather and delivery engines. A receipt is replay evidence, not an
author signature. No filesystem writes or dynamic code execution occur.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _json, _limit, _object
from skeleton.game.gameplay.scene_weather import _export
from skeleton.game.gameplay.scene_weather_market import (
    MAX_FEE_BPS, MAX_MARKET_STEPS, MAX_REPUTATION_BONUS,
    new_market, normalize_market, original_market, resume_market,
    verify_market,
)

SCHEMA = "skeleton.weather_market_author.v1"
MAX_EDITS = 16
FIELDS = {
    "set-commission": ("commission_bps", 0, MAX_FEE_BPS),
    "set-early-threshold": ("early_by_ticks", 1, MAX_MARKET_STEPS),
    "set-reputation": ("early_reputation", 0, MAX_REPUTATION_BONUS),
}


def _operations(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise SceneTravelError("invalid weather market edit count")
    checked: list[dict[str, Any]] = []
    touched: set[tuple[str, str]] = set()
    for item in raw:
        op = _object(item, {"kind", "delivery_id", "value"},
                     "weather market edit")
        kind = op["kind"]
        if type(kind) is not str or kind not in FIELDS:
            raise SceneTravelError("unsupported weather market edit")
        delivery_id = _id(op["delivery_id"], "market delivery_id")
        field, low, high = FIELDS[kind]
        value = _limit(op["value"], field, low, high)
        identity = (delivery_id, field)
        if identity in touched:
            raise SceneTravelError("duplicate weather market edit target")
        touched.add(identity)
        checked.append({"kind": kind, "delivery_id": delivery_id, "value": value})
    return checked


def edit_market(source: Any, operations: Any, expected_digest: Any,
                *, actions: Any = None) -> dict[str, Any]:
    """Apply all edits atomically, validate the full source, then play preview."""
    original = normalize_market(source)
    if type(expected_digest) is not str or expected_digest != dig(original):
        raise SceneTravelError("stale weather market source digest")
    ops = _operations(operations)
    changed = copy.deepcopy(original)
    contracts = {item["delivery_id"]: item for item in changed["contracts"]}
    for op in ops:
        contract = contracts.get(op["delivery_id"])
        if contract is None:
            raise SceneTravelError("weather market edit references unknown delivery")
        field = FIELDS[op["kind"]][0]
        contract[field] = op["value"]
    changed = normalize_market(changed)
    if changed == original:
        raise SceneTravelError("weather market edit has no effect")
    if actions is not None and type(actions) is not list:
        raise SceneTravelError("invalid weather market preview actions")
    initial = new_market(changed)
    preview = (initial if actions is None
               else resume_market(initial, actions))
    result = {
        "schema_version": SCHEMA,
        "before_digest": dig(original),
        "after_digest": dig(changed),
        "operations": ops,
        "source": changed,
        "preview_session": preview,
        "preview_state_digest": preview["state_digest"],
        "preview_actions": [] if actions is None else actions,
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def verify_market_edit(source: Any, raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "before_digest", "after_digest", "operations",
        "source", "preview_session", "preview_state_digest",
        "preview_actions", "receipt",
    }, "weather market edit receipt")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported weather market edit schema")
    _export(obj)
    expected = edit_market(
        source, obj["operations"], obj["before_digest"],
        actions=obj["preview_actions"],
    )
    if expected != obj:
        raise SceneTravelError("weather market authoring receipt or preview mismatch")
    if verify_market(obj["preview_session"]) != obj["preview_session"]:
        raise SceneTravelError("weather market preview replay mismatch")
    return expected


def original_author_demo() -> tuple[dict[str, Any], dict[str, Any]]:
    source, actions = original_market()
    receipt = edit_market(
        source,
        [{"kind": "set-commission", "delivery_id": "gate_supply", "value": 2000}],
        dig(normalize_market(source)), actions=actions,
    )
    return source, receipt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton weather-market-author",
        description="Source-fenced offline caravan market editing and preview",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--actions-json")
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            _, result = original_author_demo()
        elif args.command == "edit":
            actions = (_json(args.actions_json, "preview actions")
                       if args.actions_json is not None else None)
            result = edit_market(
                _json(args.source_json, "market source"),
                _json(args.operations_json, "market edits"),
                args.expected_digest, actions=actions,
            )
        else:
            result = verify_market_edit(
                _json(args.source_json, "market source"),
                _json(args.receipt_json, "market receipt"),
            )
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
