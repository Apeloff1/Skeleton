"""Read-only, replay-derived expedition economy and alternate-save audit."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_expedition import (
    _advance, new_expedition, original_expedition,
    simulate_expedition, verify_expedition,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, MAX_CLI_BYTES, _parse_json

SCHEMA = "skeleton.arena_expedition_economy_audit.v1"
COMPARE_SCHEMA = "skeleton.arena_expedition_economy_compare.v1"


def audit_expedition(payload: Any) -> dict[str, Any]:
    """Reconstruct earned credits, purchases and consumables from actual play."""
    saved = verify_expedition(payload)
    current = new_expedition(saved["source"])
    shop = {item["id"]: item for item in saved["source"]["shop"]}
    timeline: list[dict[str, Any]] = []
    earned = spent = 0
    for event in saved["journal"]:
        action = event["action"]
        before = current["state"]
        advanced = _advance(current, action)
        after = advanced["state"]
        delta = after["currency"] - before["currency"]
        kind = action["kind"]
        item_id = action.get("item_id")
        credit = delta if kind in ("fight", "fight_tactical") else 0
        debit = shop[item_id]["price"] if kind == "buy" else 0
        if credit < 0 or delta != credit - debit:
            raise CombatSessionError("expedition accounting delta mismatch")
        if kind in ("fight", "fight_tactical"):
            if after["arenas"][-1]["reward"] != credit:
                raise CombatSessionError("expedition reward mismatch")
        earned += credit
        spent += debit
        before_items, after_items = before["inventory"], after["inventory"]
        changes = {
            key: after_items.get(key, 0) - before_items.get(key, 0)
            for key in sorted(set(before_items) | set(after_items))
            if after_items.get(key, 0) != before_items.get(key, 0)
        }
        expected_changes = (
            {item_id: 1} if kind == "buy" else
            {item_id: -1} if kind == "use" else {}
        )
        if changes != expected_changes:
            raise CombatSessionError("expedition inventory ledger mismatch")
        timeline.append({
            "sequence": event["sequence"], "kind": kind,
            "item_id": item_id,
            "arena_id": (
                after["arenas"][-1]["arena_id"]
                if kind in ("fight", "fight_tactical") else None
            ),
            "earned": credit, "spent": debit,
            "currency_before": before["currency"],
            "currency_after": after["currency"],
            "hp_before": before["hero_hp"],
            "hp_after": after["hero_hp"],
            "inventory_delta": changes,
            "state_digest": advanced["state_digest"],
            "event_receipt": event["receipt"],
        })
        current = advanced
    if current != saved or earned - spent != saved["state"]["currency"]:
        raise CombatSessionError("expedition accounting reconciliation mismatch")
    remaining = {
        item["id"]: item["stock"] - saved["state"]["purchased"].get(item["id"], 0)
        for item in saved["source"]["shop"]
    }
    if any(stock < 0 for stock in remaining.values()):
        raise CombatSessionError("expedition negative shop stock")
    report = {
        "schema_version": SCHEMA,
        "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"],
        "event_bus_digest": saved["event_bus_digest"],
        "phase": saved["state"]["phase"],
        "hero_hp": saved["state"]["hero_hp"],
        "total_earned": earned, "total_spent": spent,
        "balance": saved["state"]["currency"],
        "inventory": dict(sorted(saved["state"]["inventory"].items())),
        "shop_remaining": remaining, "timeline": timeline,
    }
    report["checksum"] = dig(report)
    return report


def verify_audit(payload: Any, *, session: Any) -> dict[str, Any]:
    expected = audit_expedition(session)
    if type(payload) is not dict or payload != expected:
        raise CombatSessionError("expedition audit replay mismatch")
    return expected


def compare_expeditions(left: Any, right: Any) -> dict[str, Any]:
    """Require same source, independently verify both save branches."""
    lhs, rhs = verify_expedition(left), verify_expedition(right)
    if lhs["source_digest"] != rhs["source_digest"]:
        raise CombatSessionError("cannot compare different expedition sources")
    la, ra = audit_expedition(lhs), audit_expedition(rhs)
    common = 0
    for a, b in zip(lhs["journal"], rhs["journal"]):
        if a["action"] != b["action"] or a["receipt"] != b["receipt"]:
            break
        common += 1
    def summary(save: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
        return {
            "state_digest": save["state_digest"],
            "audit_checksum": audit["checksum"],
            "phase": save["state"]["phase"],
            "earned": audit["total_earned"], "spent": audit["total_spent"],
            "balance": audit["balance"], "hero_hp": audit["hero_hp"],
        }
    report = {
        "schema_version": COMPARE_SCHEMA,
        "source_digest": lhs["source_digest"],
        "common_action_prefix": common,
        "left_actions": len(lhs["journal"]),
        "right_actions": len(rhs["journal"]),
        "same_state": lhs["state_digest"] == rhs["state_digest"],
        "left": summary(lhs, la), "right": summary(rhs, ra),
    }
    report["checksum"] = dig(report)
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-expedition-audit")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name, fields in {
        "audit": ("session-json",),
        "verify": ("session-json", "audit-json"),
        "compare": ("left-json", "right-json"),
    }.items():
        cmd = sub.add_parser(name)
        for field in fields:
            cmd.add_argument("--" + field, required=True)
    args = parser.parse_args(list(argv))
    try:
        def read(name: str) -> Any:
            return _parse_json(getattr(args, name.replace("-", "_")), name)
        if args.command == "demo":
            saved = simulate_expedition(original_expedition(), [
                {"kind": "fight"}, {"kind": "buy", "item_id": "tide_tonic"},
                {"kind": "use", "item_id": "tide_tonic"}, {"kind": "fight"},
            ])
            result = audit_expedition(saved)
        elif args.command == "audit":
            result = audit_expedition(read("session-json"))
        elif args.command == "verify":
            result = verify_audit(read("audit-json"), session=read("session-json"))
        else:
            result = compare_expeditions(read("left-json"), read("right-json"))
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
            raise CombatSessionError("expedition audit output exceeds size budget")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
