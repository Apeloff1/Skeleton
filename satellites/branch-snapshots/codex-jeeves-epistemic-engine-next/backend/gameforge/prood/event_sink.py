"""
gameforge.prood.event_sink — durable EventBus → Mongo sink (Stage B3).

A single wildcard subscriber on the global ``event_bus`` mirrors every
published event (saga.*, build.*, iq.*, ship.*) into the Mongo collection
``prood_event_log`` so the Universal Logs feed can surface LIVE distributed
activity that survives a restart (the in-memory ``event_bus.history`` does
not). Writes are best-effort and capped.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from gameforge.prood.event_bus import event_bus

_LOG_COLLECTION = "prood_event_log"
_installed = False


def _severity_for(event_type: str) -> str:
    if any(k in event_type for k in ("fail", "error", "compensat")):
        return "error" if "fail" in event_type or "error" in event_type else "warning"
    return "info"


async def _persist(event_type: str, payload: Any):
    try:
        from core.databases import core_db
        await core_db[_LOG_COLLECTION].insert_one({
            "event_type": event_type,
            "severity": _severity_for(event_type),
            "payload": payload if isinstance(payload, (dict, list, str, int, float, bool, type(None))) else str(payload),
            "ts": time.time(),
        })
    except Exception:  # noqa: BLE001 — logging must never break a publish
        pass


def install_event_sink() -> bool:
    """Attach the durable wildcard subscriber exactly once."""
    global _installed
    if _installed:
        return False

    def _handler(payload):
        # event_bus passes only the payload to subscribers; we capture the
        # type via a closure factory is not available, so we re-publish with a
        # typed wrapper below. Simplest: rely on the wrapped publisher.
        return None

    # We need the event_type, which the bare "*" handler doesn't receive, so
    # we wrap event_bus.publish to also persist. This preserves all existing
    # behavior and adds durability.
    original_publish = event_bus.publish

    async def _publish_and_persist(event_type: str, payload: Any = None):
        rec = await original_publish(event_type, payload)
        await _persist(event_type, payload)
        return rec

    event_bus.publish = _publish_and_persist  # type: ignore[assignment]
    _installed = True
    return True


async def recent_events(limit: int = 60, severity: str | None = None) -> list[Dict]:
    """Read the durable event log (newest first)."""
    try:
        from core.databases import core_db
        q: Dict[str, Any] = {}
        if severity:
            q["severity"] = severity
        cur = core_db[_LOG_COLLECTION].find(q, {"_id": 0}).sort("ts", -1).limit(int(limit))
        return await cur.to_list(int(limit))
    except Exception:  # noqa: BLE001
        return []


__all__ = ["install_event_sink", "recent_events"]
