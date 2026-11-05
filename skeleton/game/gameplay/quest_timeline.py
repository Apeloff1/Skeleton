"""Replay-verified quest reward timeline and save-branch comparison.

All currency and inventory deltas come from canonical QuestEngine transitions.
A serialized save is never trusted as an independent source of rewards.
"""
from __future__ import annotations

from typing import Any

from .quest_session import (
    GameplayContractError, QuestEngine, QuestTrigger, _digest,
)

SCHEMA = "skeleton.quest_timeline.v1"


def inspect_journal(engine: QuestEngine, saved: Any) -> dict[str, Any]:
    """Restore and replay each event to expose exact reward consequences."""
    if not isinstance(engine, QuestEngine):
        raise GameplayContractError("invalid quest timeline engine")
    session = engine.restore(saved)
    cursor = engine.new_session()
    timeline = []
    for trigger in session.events:
        before = cursor
        cursor = engine._apply_verified(cursor, trigger)
        old_items = dict(before.inventory)
        new_items = dict(cursor.inventory)
        deltas = {
            item: new_items.get(item, 0) - old_items.get(item, 0)
            for item in sorted(set(old_items) | set(new_items))
            if new_items.get(item, 0) != old_items.get(item, 0)
        }
        event = {
            "sequence": trigger.sequence,
            "quest_id": trigger.quest_id,
            "trigger": trigger.as_record(),
            "before_digest": before.state_digest,
            "after_digest": cursor.state_digest,
            "currency_before": before.currency,
            "currency_after": cursor.currency,
            "currency_delta": cursor.currency - before.currency,
            "item_deltas": deltas,
            "completed": list(cursor.completed),
            "ending_id": cursor.ending_id,
            "save_digest": cursor.save_metadata.digest,
        }
        event["receipt"] = _digest(event)
        timeline.append(event)
    if cursor != session:
        raise GameplayContractError("quest timeline replay mismatch")
    report = {
        "schema_version": SCHEMA,
        "world_id": engine.plan.world_id,
        "plan_digest": engine.plan.digest,
        "state_digest": session.state_digest,
        "save_digest": session.save_metadata.digest,
        "event_count": len(timeline),
        "currency": session.currency,
        "inventory": [[item, count] for item, count in session.inventory],
        "ending_id": session.ending_id,
        "timeline": timeline,
    }
    report["checksum"] = _digest(report)
    return report


def compare_journals(
    engine: QuestEngine, left: Any, right: Any,
) -> dict[str, Any]:
    """Compare replay-verified histories from the exact same authored plan."""
    a = engine.restore(left)
    b = engine.restore(right)
    prefix = 0
    while (prefix < min(len(a.events), len(b.events))
           and a.events[prefix] == b.events[prefix]):
        prefix += 1
    if a == b:
        relationship = "identical"
    elif prefix == min(len(a.events), len(b.events)):
        relationship = "prefix"
    else:
        relationship = "divergent"
    result = {
        "schema_version": SCHEMA,
        "plan_digest": engine.plan.digest,
        "relationship": relationship,
        "common_events": prefix,
        "first_divergent_event": (
            prefix if relationship == "divergent" else None
        ),
        "left": {
            "events": len(a.events),
            "state_digest": a.state_digest,
            "save_digest": a.save_metadata.digest,
            "currency": a.currency,
            "inventory": [[item, count] for item, count in a.inventory],
            "ending_id": a.ending_id,
        },
        "right": {
            "events": len(b.events),
            "state_digest": b.state_digest,
            "save_digest": b.save_metadata.digest,
            "currency": b.currency,
            "inventory": [[item, count] for item, count in b.inventory],
            "ending_id": b.ending_id,
        },
    }
    result["checksum"] = _digest(result)
    return result


def verify_timeline(
    engine: QuestEngine, saved: Any, report: Any,
) -> dict[str, Any]:
    """Recompute all event and final receipts; fail closed on any alteration."""
    expected = inspect_journal(engine, saved)
    if type(report) is not dict or report != expected:
        raise GameplayContractError("quest timeline receipt mismatch")
    return expected


def verify_comparison(
    engine: QuestEngine, left: Any, right: Any, report: Any,
) -> dict[str, Any]:
    expected = compare_journals(engine, left, right)
    if type(report) is not dict or report != expected:
        raise GameplayContractError("quest comparison receipt mismatch")
    return expected
