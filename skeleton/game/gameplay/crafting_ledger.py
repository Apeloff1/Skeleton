"""Replay-verified item and currency provenance for offline crafting sessions.

All events are derived from a canonical CraftEngine replay, never from
client-supplied balances. This is game currency only, not a payment ledger.
"""
from __future__ import annotations

import json
from typing import Any

from .crafting_runtime import (
    CraftEngine, CraftState, GameplayContractError, MAX_EVENTS, _digest,
)

SCHEMA = "skeleton.crafting_ledger.v1"
MAX_REPORT_BYTES = 1_048_576


def _size(value: Any) -> None:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise GameplayContractError("invalid crafting ledger JSON") from exc
    if len(encoded) > MAX_REPORT_BYTES:
        raise GameplayContractError("crafting ledger exceeds portable size budget")


def _delta(before: CraftState, after: CraftState) -> list[list[object]]:
    left = dict(before.inventory)
    right = dict(after.inventory)
    return [
        [item, right.get(item, 0) - left.get(item, 0)]
        for item in sorted(set(left) | set(right))
        if right.get(item, 0) != left.get(item, 0)
    ]


def inspect_ledger(engine: CraftEngine, saved: Any) -> dict[str, Any]:
    """Reconstruct every receipt and exact ingredient/currency change."""
    if not isinstance(engine, CraftEngine):
        raise GameplayContractError("invalid crafting ledger engine")
    final = engine.restore(saved)
    if len(final.actions) > MAX_EVENTS:
        raise GameplayContractError("crafting ledger event budget exceeded")
    cursor = engine.start()
    events = []
    spent = 0
    consumed: dict[str, int] = {}
    produced: dict[str, int] = {}
    for action in final.actions:
        recipe = engine.plan.by_id[action.recipe_id]
        after = engine._apply_verified(cursor, action)
        inputs = [[item, count * action.batches] for item, count in recipe.consumes]
        outputs = [[item, count * action.batches] for item, count in recipe.produces]
        for item, amount in inputs:
            consumed[item] = consumed.get(item, 0) + amount
        for item, amount in outputs:
            produced[item] = produced.get(item, 0) + amount
        fee = recipe.currency_cost * action.batches
        if cursor.currency - after.currency != fee:
            raise GameplayContractError("crafting currency conservation mismatch")
        spent += fee
        event = {
            "sequence": action.sequence,
            "action": action.record(),
            "before_digest": cursor.digest,
            "after_digest": after.digest,
            "currency_before": cursor.currency,
            "currency_after": after.currency,
            "currency_spent": fee,
            "consumed": inputs,
            "produced": outputs,
            "inventory_delta": _delta(cursor, after),
            "new_flags": sorted(set(after.flags) - set(cursor.flags)),
        }
        event["receipt"] = _digest(event)
        events.append(event)
        cursor = after
    if cursor != final:
        raise GameplayContractError("crafting ledger replay differs from save")
    if engine.plan.initial_currency - final.currency != spent:
        raise GameplayContractError("crafting total currency mismatch")
    report = {
        "schema_version": SCHEMA,
        "world_id": engine.plan.world_id,
        "plan_digest": engine.plan.digest,
        "initial_state_digest": engine.start().digest,
        "final_state_digest": final.digest,
        "total_currency_spent": spent,
        "total_consumed": [[item, consumed[item]] for item in sorted(consumed)],
        "total_produced": [[item, produced[item]] for item in sorted(produced)],
        "events": events,
        "save": final.save_record(),
    }
    report["checksum"] = _digest(report)
    _size(report)
    return report


def verify_ledger(engine: CraftEngine, raw: Any) -> dict[str, Any]:
    """Replay the saved game and compare every claimed ledger transition."""
    _size(raw)
    if type(raw) is not dict or set(raw) != {
        "schema_version", "world_id", "plan_digest", "initial_state_digest",
        "final_state_digest", "total_currency_spent", "total_consumed",
        "total_produced", "events", "save", "checksum",
    }:
        raise GameplayContractError("invalid crafting ledger fields")
    if raw["schema_version"] != SCHEMA:
        raise GameplayContractError("unsupported crafting ledger schema")
    if raw["plan_digest"] != engine.plan.digest:
        raise GameplayContractError("crafting ledger plan identity mismatch")
    expected = inspect_ledger(engine, raw["save"])
    if raw != expected:
        raise GameplayContractError("crafting ledger replay or checksum mismatch")
    return expected
