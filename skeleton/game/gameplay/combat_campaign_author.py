"""Transactional offline combat campaign authoring with replay-proven previews.

Source and receipts are untrusted JSON. Digests detect drift, not authorship;
authorization and provenance belong to the application boundary.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_campaign import (
    MAX_CURRENCY, MAX_ENCOUNTER_TURNS, finish_campaign,
    normalize_campaign, original_campaign,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_author.v1"
MAX_EDITS = 24
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STAT_LIMITS = {
    "max_hp": (1, 10000),
    "attack": (1, 1000),
    "defense": (0, 1000),
    "speed": (0, 1000),
}


def _bounded_json(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise CombatSessionError("invalid authoring export") from exc
    if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
        raise CombatSessionError("authoring export exceeds 128 KiB")
    return encoded


def _validated_operations(raw: Any) -> list[dict[str, Any]]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_EDITS:
        raise CombatSessionError("invalid authoring edit count")
    edits: list[dict[str, Any]] = []
    for item in raw:
        if type(item) is not dict:
            raise CombatSessionError("invalid authoring edit")
        kind = item.get("kind")
        if kind == "set-reward":
            _object(item, {"kind", "encounter_id", "value"}, "reward edit")
            value = _integer(item["value"], "reward", 0, MAX_CURRENCY)
            edits.append({"kind": kind, "encounter_id": _id(item["encounter_id"], "encounter_id"),
                          "value": value})
        elif kind == "set-turn-limit":
            _object(item, {"kind", "encounter_id", "value"}, "turn edit")
            value = _integer(item["value"], "turn_limit", 1, MAX_ENCOUNTER_TURNS)
            edits.append({"kind": kind, "encounter_id": _id(item["encounter_id"], "encounter_id"),
                          "value": value})
        elif kind == "set-foe-stat":
            _object(item, {"kind", "encounter_id", "actor_id", "stat", "value"}, "foe edit")
            stat = item["stat"]
            if type(stat) is not str or stat not in _STAT_LIMITS:
                raise CombatSessionError("unsupported foe stat")
            low, high = _STAT_LIMITS[stat]
            edits.append({
                "kind": kind, "encounter_id": _id(item["encounter_id"], "encounter_id"),
                "actor_id": _id(item["actor_id"], "actor_id"), "stat": stat,
                "value": _integer(item["value"], stat, low, high),
            })
        else:
            raise CombatSessionError("unsupported campaign edit kind")
    return edits


def author_campaign(source: Any, operations: Any, expected_source_digest: Any) -> dict[str, Any]:
    """Apply all edits atomically, compile canonical source and preview real gameplay."""
    before = normalize_campaign(source)
    before_digest = dig(before)
    if (type(expected_source_digest) is not str
            or _SHA256.fullmatch(expected_source_digest) is None
            or expected_source_digest != before_digest):
        raise CombatSessionError("stale or invalid campaign source digest")
    edits = _validated_operations(operations)
    # Never mutate the caller's source, even if the last edit is rejected.
    candidate = json.loads(_bounded_json(before))
    for edit in edits:
        encounter = next(
            (entry for entry in candidate["encounters"]
             if entry["scenario"]["encounter_id"] == edit["encounter_id"]), None
        )
        if encounter is None:
            raise CombatSessionError("unknown authored encounter")
        if edit["kind"] == "set-reward":
            current, container, key = encounter["reward"], encounter, "reward"
        elif edit["kind"] == "set-turn-limit":
            container, key = encounter["scenario"], "turn_limit"
            current = container[key]
        else:
            actor = next(
                (actor for actor in encounter["scenario"]["actors"]
                 if actor["id"] == edit["actor_id"]), None
            )
            if actor is None or actor["id"] == candidate["hero_id"]:
                raise CombatSessionError("foe edit cannot modify hero or unknown actor")
            container, key = actor, edit["stat"]
            current = container[key]
        if current == edit["value"]:
            raise CombatSessionError("authoring no-op edit")
        container[key] = edit["value"]
    compiled = normalize_campaign(candidate)
    after_digest = dig(compiled)
    if after_digest == before_digest:
        raise CombatSessionError("authoring transaction has no net change")
    preview = finish_campaign(compiled)
    result = {
        "schema_version": SCHEMA,
        "before_digest": before_digest,
        "after_digest": after_digest,
        "operations": edits,
        "source": compiled,
        "preview_session": preview,
        "preview_state_digest": preview["state_digest"],
        "claim": "offline_replay_preview_only",
    }
    result["receipt"] = dig(result)
    _bounded_json(result)
    return result


def verify_authoring(source: Any, receipt: Any) -> dict[str, Any]:
    """Re-execute edits and every encounter, including save lineage, from original source."""
    obj = _object(receipt, {
        "schema_version", "before_digest", "after_digest", "operations",
        "source", "preview_session", "preview_state_digest", "claim", "receipt",
    }, "campaign authoring receipt")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "offline_replay_preview_only":
        raise CombatSessionError("unsupported authoring receipt schema or claim")
    _bounded_json(obj)
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("authoring receipt digest mismatch")
    expected = author_campaign(source, obj["operations"], obj["before_digest"])
    if expected != obj:
        raise CombatSessionError("authoring source, preview or replay mismatch")
    return expected


def original_authoring_demo() -> dict[str, Any]:
    source = original_campaign()
    return author_campaign(source, [
        {"kind": "set-reward", "encounter_id": "reed_watch", "value": 12},
        {"kind": "set-foe-stat", "encounter_id": "tide_gate",
         "actor_id": "mireling", "stat": "defense", "value": 2},
    ], dig(normalize_campaign(source)))


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Edit and replay an original offline campaign")
    edit = sub.add_parser("edit", help="Apply source-fenced edits with real gameplay preview")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    check = sub.add_parser("verify", help="Verify an edit receipt against original source")
    check.add_argument("--source-json", required=True)
    check.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_authoring_demo()
        else:
            source = _parse_json(args.source_json, "campaign source")
            if args.command == "edit":
                result = author_campaign(
                    source, _parse_json(args.operations_json, "campaign edits"),
                    args.expected_digest,
                )
            else:
                result = verify_authoring(
                    source, _parse_json(args.receipt_json, "authoring receipt"),
                )
        print(_bounded_json(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
