"""Source-bound checkpoint-to-checkpoint economy reconciliation.

Only an append-only canonical market journal is a valid continuation. A save
from a fork, different source, or fabricated receipt is never merged silently.
"""
from __future__ import annotations

from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _bounded, verify_market
from skeleton.game.gameplay.scene_market_ledger import audit_market_ledger
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_reconciliation.v1"


def _change(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {
        key: after.get(key, 0) - before.get(key, 0)
        for key in sorted(before.keys() | after.keys())
        if before.get(key, 0) != after.get(key, 0)
    }


def reconcile_market(before: Any, after: Any) -> dict[str, Any]:
    """Prove an append-only replay and the exact net economic changes."""
    first = verify_market(before)
    last = verify_market(after)
    if first["source_digest"] != last["source_digest"]:
        raise SceneTravelError("market reconciliation source mismatch")
    prefix = len(first["journal"])
    if (prefix > len(last["journal"])
            or first["journal"] != last["journal"][:prefix]):
        raise SceneTravelError("market reconciliation requires append-only journal")
    prior = audit_market_ledger(first)
    current = audit_market_ledger(last)
    delta = current["entries"][prefix:]
    if len(delta) != len(last["journal"]) - prefix:
        raise SceneTravelError("market reconciliation action count mismatch")
    state_before, state_after = first["state"], last["state"]
    credits = state_after["credits"] - state_before["credits"]
    reputation = state_after["reputation"] - state_before["reputation"]
    goods = _change(state_before["goods"], state_after["goods"])
    purchases = _change(state_before["purchases"], state_after["purchases"])
    crafted = _change(state_before["crafted"], state_after["crafted"])
    delivered = sorted(set(state_after["delivered"]) -
                       set(state_before["delivered"]))
    if (credits != sum(row["credit_delta"] for row in delta)
            or reputation != sum(row["reputation_delta"] for row in delta)
            or goods != _sum_goods(delta)
            or any(value < 0 for value in purchases.values())
            or any(value < 0 for value in crafted.values())
            or not set(state_before["delivered"]) <= set(state_after["delivered"])
            or current["credits_earned"] < prior["credits_earned"]
            or current["credits_spent"] < prior["credits_spent"]):
        raise SceneTravelError("market reconciliation conservation mismatch")
    report = {
        "schema_version": SCHEMA,
        "source_digest": first["source_digest"],
        "from_state_digest": first["state_digest"],
        "to_state_digest": last["state_digest"],
        "from_save_digest": dig(first["save"]),
        "to_save_digest": dig(last["save"]),
        "from_tick": state_before["tick"],
        "to_tick": state_after["tick"],
        "actions_applied": len(delta),
        "appended_receipts": [row["event_receipt"] for row in delta],
        "credits_delta": credits,
        "credits_earned_delta": (current["credits_earned"] -
                                 prior["credits_earned"]),
        "credits_spent_delta": (current["credits_spent"] -
                                prior["credits_spent"]),
        "goods_delta": goods, "purchases_delta": purchases,
        "crafted_delta": crafted, "new_deliveries": delivered,
        "reputation_delta": reputation,
        "from_phase": state_before["phase"],
        "to_phase": state_after["phase"],
        "from_ledger_checksum": prior["checksum"],
        "to_ledger_checksum": current["checksum"],
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def _sum_goods(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        for item, quantity in row["goods_delta"].items():
            totals[item] = totals.get(item, 0) + quantity
    return {key: value for key, value in sorted(totals.items()) if value}
