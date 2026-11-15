"""Restart-safe PROOD event delivery via the local transactional outbox."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict

from gameforge.prood.event_bus import event_bus
from zaibatsu.outbox import Outbox

_LOG_COLLECTION = "prood_event_log"
_installed = False
_outbox: Outbox | None = None
_admission_failures = 0


def _severity_for(event_type: str) -> str:
    if any(k in event_type for k in ("fail", "error", "compensat")):
        return "error" if "fail" in event_type or "error" in event_type else "warning"
    return "info"


async def _mongo_sink(collection: str, document: dict) -> bool:
    from core.databases import core_db
    if collection != _LOG_COLLECTION:
        raise ValueError("unexpected PROOD collection")
    delivery_id = document["_outbox_id"]
    body = {key: value for key, value in document.items() if key != "_outbox_id"}
    # Crash after remote commit but before local acknowledgement is safe:
    # Mongo's unique _id plus setOnInsert gives replay the same identity.
    await core_db[collection].update_one(
        {"_id": delivery_id}, {"$setOnInsert": body}, upsert=True)
    return True


def _journal() -> Outbox:
    global _outbox
    if _outbox is None:
        path = os.environ.get("PROOD_EVENT_OUTBOX_PATH") or (
            Path(__file__).resolve().parents[2] / "data" / "zaibatsu" / "prood.sqlite3")
        _outbox = Outbox(_mongo_sink, path=path, cap=4096)
    return _outbox


async def _persist(event_type: str, payload: Any) -> str:
    global _admission_failures
    try:
        if type(event_type) is not str or not 1 <= len(event_type) <= 128:
            raise ValueError("invalid event type")
        await _journal().journal(_LOG_COLLECTION, {
            "event_type": event_type,
            "severity": _severity_for(event_type),
            "payload": payload,
            "ts": time.time(),
        })
        return "journaled"
    except Exception:
        _admission_failures += 1
        return "unavailable"


async def flush_pending_events(limit: int = 128) -> dict:
    journal = _journal()
    confirmed = await journal.reconcile(limit=limit)
    return {"confirmed": confirmed, "pending": await journal.pending_count(),
            "admission_failures": _admission_failures,
            "scope": "local_outbox_to_mongo"}


def install_event_sink() -> bool:
    """Journal before fanout; preserve subscriber behavior and report custody."""
    global _installed
    if _installed:
        return False
    original_publish = event_bus.publish

    async def _publish_and_persist(event_type: str, payload: Any = None):
        custody = await _persist(event_type, payload)
        record = await original_publish(event_type, payload)
        record["persistence"] = custody
        return record

    event_bus.publish = _publish_and_persist  # type: ignore[assignment]
    _installed = True
    return True


async def recent_events(limit: int = 60, severity: str | None = None) -> list[Dict]:
    """Read confirmed durable events, newest first."""
    try:
        from core.databases import core_db
        q: Dict[str, Any] = {}
        if severity:
            q["severity"] = severity
        bound = max(1, min(int(limit), 500))
        cur = core_db[_LOG_COLLECTION].find(q, {"_id": 0}).sort("ts", -1).limit(bound)
        return await cur.to_list(bound)
    except Exception:
        return []


__all__ = ["install_event_sink", "recent_events", "flush_pending_events"]
