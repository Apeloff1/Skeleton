"""Atomic weather delivery editor with playable, bounded route preview.

No operation changes the caller's source or bypasses canonical weather travel.
A source digest is an optimistic concurrency lease, not user authorization.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _json, _object
from skeleton.game.gameplay.scene_weather import _export
from skeleton.game.gameplay.scene_weather_delivery import (
    MAX_DELIVERIES, normalize_deliveries, original_deliveries,
)
from skeleton.game.gameplay.scene_weather_delivery_solver import plan_deliveries

SCHEMA = "skeleton.weather_deliveries_author.v1"
MAX_EDITS = 16
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {
    "set-deadline": "deadline", "set-reward": "reward",
    "set-destination": "destination_scene", "set-item": "required_item",
    "set-requires": "requires",
}


def _edits(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise SceneTravelError("invalid delivery edit count")
    result: list[dict[str, Any]] = []
    for entry in raw:
        if type(entry) is not dict:
            raise SceneTravelError("invalid delivery edit")
        kind = entry.get("kind")
        if kind == "add-delivery":
            item = _object(entry, {"kind", "delivery"}, "delivery addition")
            if type(item["delivery"]) is not dict:
                raise SceneTravelError("invalid authored delivery")
            result.append({"kind": kind, "delivery": item["delivery"]})
        elif kind == "remove-delivery":
            item = _object(entry, {"kind", "delivery_id"}, "delivery removal")
            result.append({
                "kind": kind, "delivery_id": _id(item["delivery_id"], "delivery_id"),
            })
        elif kind in FIELDS:
            item = _object(entry, {"kind", "delivery_id", "value"}, "delivery edit")
            result.append({
                "kind": kind, "delivery_id": _id(item["delivery_id"], "delivery_id"),
                "value": item["value"],
            })
        else:
            raise SceneTravelError("unsupported delivery edit kind")
    _export(result)
    return result


def author_deliveries(source: Any, operations: Any,
                      expected_source_digest: Any) -> dict[str, Any]:
    before = normalize_deliveries(source)
    before_digest = dig(before)
    if (type(expected_source_digest) is not str
            or SHA256.fullmatch(expected_source_digest) is None
            or expected_source_digest != before_digest):
        raise SceneTravelError("stale or invalid delivery source digest")
    edits = _edits(operations)
    candidate = json.loads(_export(before))
    for edit in edits:
        kind = edit["kind"]
        if kind == "add-delivery":
            if len(candidate["deliveries"]) >= MAX_DELIVERIES:
                raise SceneTravelError("delivery authoring capacity exceeded")
            candidate["deliveries"].append(edit["delivery"])
            continue
        index = next(
            (i for i, entry in enumerate(candidate["deliveries"])
             if entry["delivery_id"] == edit["delivery_id"]), None
        )
        if index is None:
            raise SceneTravelError("unknown authored delivery")
        if kind == "remove-delivery":
            candidate["deliveries"].pop(index)
            continue
        field = FIELDS[kind]
        if candidate["deliveries"][index][field] == edit["value"]:
            raise SceneTravelError("delivery authoring no-op edit")
        candidate["deliveries"][index][field] = edit["value"]
    compiled = normalize_deliveries(candidate)
    after_digest = dig(compiled)
    if after_digest == before_digest:
        raise SceneTravelError("delivery authoring has no net change")
    # Search uses the same weather, inventory, collision and deadline contracts
    # as interactive play. Exhaustion is reported, never called success.
    preview = plan_deliveries(compiled, max_states=128, max_depth=16)
    result = {
        "schema_version": SCHEMA,
        "before_digest": before_digest, "after_digest": after_digest,
        "operations": edits, "source": compiled,
        "preview_route": preview,
        "claim": "bounded_offline_route_preview_only",
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def verify_delivery_authoring(source: Any, raw: Any) -> dict[str, Any]:
    receipt = _object(raw, {
        "schema_version", "before_digest", "after_digest", "operations",
        "source", "preview_route", "claim", "receipt",
    }, "delivery authoring receipt")
    if (receipt["schema_version"] != SCHEMA
            or receipt["claim"] != "bounded_offline_route_preview_only"):
        raise SceneTravelError("unsupported delivery authoring receipt")
    _export(receipt)
    if receipt["receipt"] != dig({k: v for k, v in receipt.items() if k != "receipt"}):
        raise SceneTravelError("delivery authoring receipt digest mismatch")
    expected = author_deliveries(source, receipt["operations"], receipt["before_digest"])
    if expected != receipt:
        raise SceneTravelError("delivery authoring source or preview mismatch")
    return expected


def original_authoring_demo() -> dict[str, Any]:
    source, _ = original_deliveries()
    return author_deliveries(source, [
        {"kind": "set-reward", "delivery_id": "gate_supply", "value": 12},
    ], dig(normalize_deliveries(source)))


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton weather-deliveries-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
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
            source = _json(args.source_json, "delivery source")
            if args.command == "edit":
                result = author_deliveries(
                    source, _json(args.operations_json, "delivery edits"),
                    args.expected_digest,
                )
            else:
                result = verify_delivery_authoring(
                    source, _json(args.receipt_json, "delivery authoring receipt"),
                )
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
