"""Conservation-checked NPC gift and crafting inventory provenance.

Every inventory mutation is derived from a canonical replayed quest action.
No external source can directly grant a gift, recipe output or ending item.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import (
    _advance, demo_actions, export_quest, import_quest, new_quest,
    original_quest, simulate_quest, verify_quest,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _id, _parse_json

SCHEMA = "skeleton.quest_inventory_provenance.v1"
PROOF_SCHEMA = "skeleton.quest_inventory_item_proof.v1"
MAX_BYTES = 2 * 1024 * 1024


def _bounded(payload: Any) -> None:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise CombatSessionError("invalid quest inventory audit JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise CombatSessionError("quest inventory audit exceeds size budget")


def _delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {
        item: after.get(item, 0) - before.get(item, 0)
        for item in sorted(set(before) | set(after))
        if after.get(item, 0) != before.get(item, 0)
    }


def _expected(source: dict[str, Any], action: dict[str, Any]) -> dict[str, int]:
    if action["kind"] == "talk" and action["decision"] == "aid":
        npc = next(n for n in source["npcs"] if n["id"] == action["npc_id"])
        return {npc["gift"]: 1}
    if action["kind"] == "craft":
        recipe = next(r for r in source["recipes"] if r["id"] == action["recipe_id"])
        changes = {item: -1 for item in recipe["inputs"]}
        changes[recipe["output"]] = changes.get(recipe["output"], 0) + 1
        return {key: value for key, value in changes.items() if value}
    return {}


def audit_inventory(payload: Any) -> dict[str, Any]:
    """Replay NPC and crafting changes and reconcile every unit of inventory."""
    final = verify_quest(payload)
    source = final["source"]
    current = new_quest(source)
    credits: dict[str, int] = {}
    debits: dict[str, int] = {}
    provenance = []
    for event in final["journal"]:
        action = event["action"]
        next_state = _advance(current, action)
        if next_state["journal"][-1] != event:
            raise CombatSessionError("quest inventory journal receipt mismatch")
        actual = _delta(current["state"]["items"], next_state["state"]["items"])
        expected = _expected(source, action)
        if actual != expected:
            raise CombatSessionError("quest inventory conservation mismatch")
        if actual:
            record = {
                "tick": next_state["state"]["tick"],
                "action": action,
                "action_receipt": event["receipt"],
                "changes": actual,
                "after_state_digest": next_state["state_digest"],
                "after_items": dict(sorted(next_state["state"]["items"].items())),
            }
            provenance.append(record)
            for item, count in actual.items():
                target = credits if count > 0 else debits
                target[item] = target.get(item, 0) + abs(count)
        current = next_state
    if current != final:
        raise CombatSessionError("quest inventory replay terminal mismatch")
    balance = {
        item: credits.get(item, 0) - debits.get(item, 0)
        for item in sorted(set(credits) | set(debits))
        if credits.get(item, 0) != debits.get(item, 0)
    }
    if balance != final["state"]["items"]:
        raise CombatSessionError("quest inventory balance mismatch")
    bundle = export_quest(final)
    if import_quest(bundle) != final:
        raise CombatSessionError("quest inventory portable replay mismatch")
    report = {
        "schema_version": SCHEMA,
        "source_digest": final["source_digest"],
        "final_state_digest": final["state_digest"],
        "portable_checksum": bundle["checksum"],
        "tick": final["state"]["tick"],
        "ending": final["state"]["ending"],
        "entries": provenance,
        "credits": dict(sorted(credits.items())),
        "debits": dict(sorted(debits.items())),
        "balance": balance,
        "choices": dict(sorted(final["state"]["choices"].items())),
        "crafted": list(final["state"]["crafted"]),
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def verify_audit(payload: Any, session: Any) -> dict[str, Any]:
    """Require exact replay parity; a matching digest alone is insufficient."""
    _bounded(payload)
    if type(payload) is not dict or set(payload) != {
        "schema_version", "source_digest", "final_state_digest",
        "portable_checksum", "tick", "ending", "entries", "credits",
        "debits", "balance", "choices", "crafted", "checksum",
    } or payload["schema_version"] != SCHEMA:
        raise CombatSessionError("invalid quest inventory audit")
    expected = audit_inventory(session)
    if payload != expected:
        raise CombatSessionError("quest inventory audit replay mismatch")
    return expected


def item_proof(payload: Any, item_id: str) -> dict[str, Any]:
    """Trace one item from actual NPC/recipe grants to its remaining stock."""
    item = _id(item_id, "item_id")
    audit = audit_inventory(payload)
    history = [
        {
            "tick": event["tick"],
            "action": event["action"],
            "action_receipt": event["action_receipt"],
            "delta": event["changes"][item],
            "after_count": event["after_items"].get(item, 0),
        }
        for event in audit["entries"] if item in event["changes"]
    ]
    result = {
        "schema_version": PROOF_SCHEMA,
        "source_digest": audit["source_digest"],
        "final_state_digest": audit["final_state_digest"],
        "audit_checksum": audit["checksum"],
        "item_id": item,
        "credits": audit["credits"].get(item, 0),
        "debits": audit["debits"].get(item, 0),
        "balance": audit["balance"].get(item, 0),
        "history": history,
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-inventory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    audit = sub.add_parser("audit")
    audit.add_argument("--session-json", required=True)
    proof = sub.add_parser("prove")
    proof.add_argument("--session-json", required=True)
    proof.add_argument("--item-id", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--audit-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = audit_inventory(simulate_quest(original_quest(), demo_actions()))
        elif args.command == "audit":
            result = audit_inventory(_parse_json(args.session_json, "quest session"))
        elif args.command == "prove":
            result = item_proof(
                _parse_json(args.session_json, "quest session"), args.item_id
            )
        else:
            result = verify_audit(
                _parse_json(args.audit_json, "quest audit"),
                _parse_json(args.session_json, "quest session"),
            )
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
