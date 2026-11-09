"""
PROOD EventBus — async publish/subscribe with error isolation + history.

Upgrade over the shipped stub: handler exceptions are isolated (one bad
subscriber can't break the publish), supports once() subscriptions,
unsubscribe, wildcard "*" listeners, and keeps a bounded event history for
observability.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List

_MAX_HISTORY = 500


class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self._once: Dict[str, List[Callable]] = {}
        self.history: List[Dict] = []
        self.published_count = 0
        self.error_count = 0

    def subscribe(self, event_type: str, handler: Callable) -> Callable:
        self.subscribers.setdefault(event_type, []).append(handler)
        # return an unsubscribe closure
        def _off():
            try:
                self.subscribers.get(event_type, []).remove(handler)
            except ValueError:
                pass
        return _off

    def once(self, event_type: str, handler: Callable) -> None:
        self._once.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: Any = None) -> Dict:
        self.published_count += 1
        delivered = 0
        errors: List[str] = []

        handlers = list(self.subscribers.get(event_type, [])) + list(self.subscribers.get("*", []))
        once_handlers = list(self._once.pop(event_type, []))

        for handler in handlers + once_handlers:
            try:
                res = handler(payload)
                if hasattr(res, "__await__"):
                    await res
                delivered += 1
            except Exception as e:  # noqa: BLE001 — isolate faulty subscribers
                self.error_count += 1
                errors.append(f"{type(e).__name__}: {e}")

        record = {"event_type": event_type, "delivered": delivered,
                  "errors": errors, "ts": time.time()}
        self.history.append(record)
        if len(self.history) > _MAX_HISTORY:
            self.history = self.history[-_MAX_HISTORY:]
        return record

    def stats(self) -> Dict:
        return {
            "event_types": sorted(self.subscribers.keys()),
            "subscriber_count": sum(len(v) for v in self.subscribers.values()),
            "published_count": self.published_count,
            "error_count": self.error_count,
            "history_size": len(self.history),
            "recent": self.history[-20:],
        }


# Global bus
event_bus = EventBus()
