"""Sync subscription hooks for OmniFabric appends.

Observers receive sealed ``FabricEvent`` instances after a successful
append (journal + hot-tail admit). Failures in subscribers are isolated
so a broken observer cannot roll back a durable append.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from skeleton.kernel.omnifabric.events import FabricEvent

log = logging.getLogger(__name__)

Subscriber = Callable[[FabricEvent], None]


class FabricObserver(Protocol):
    def on_event(self, ev: FabricEvent) -> None: ...


@dataclass
class Subscription:
    name: str
    callback: Subscriber
    active: bool = True
    delivered: int = 0
    errors: int = 0
    kinds: set[str] = field(default_factory=set)
    ledgers: set[str] = field(default_factory=set)

    def matches(self, ev: FabricEvent) -> bool:
        if self.kinds and ev.kind not in self.kinds:
            return False
        if self.ledgers and ev.ledger not in self.ledgers:
            return False
        return True


class SubscriberBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subs: dict[str, Subscription] = {}
        self._fanout_errors = 0

    def subscribe(
        self,
        name: str,
        callback: Subscriber,
        *,
        kinds: set[str] | None = None,
        ledgers: set[str] | None = None,
    ) -> Subscription:
        sub = Subscription(
            name=str(name),
            callback=callback,
            kinds=set(kinds or ()),
            ledgers=set(ledgers or ()),
        )
        with self._lock:
            self._subs[sub.name] = sub
        return sub

    def unsubscribe(self, name: str) -> None:
        with self._lock:
            self._subs.pop(name, None)

    def publish(self, ev: FabricEvent) -> int:
        with self._lock:
            targets = [s for s in self._subs.values() if s.active and s.matches(ev)]
        delivered = 0
        for sub in targets:
            try:
                sub.callback(ev)
                sub.delivered += 1
                delivered += 1
            except Exception:  # noqa: BLE001 — isolate observer faults
                sub.errors += 1
                self._fanout_errors += 1
                log.exception("omnifabric subscriber %s failed", sub.name)
        return delivered

    def status(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": s.name,
                    "active": s.active,
                    "delivered": s.delivered,
                    "errors": s.errors,
                    "kinds": sorted(s.kinds),
                    "ledgers": sorted(s.ledgers),
                }
                for s in self._subs.values()
            ]

    @property
    def fanout_errors(self) -> int:
        return self._fanout_errors


class RecordingObserver:
    """Test helper that records every event."""

    def __init__(self) -> None:
        self.events: list[FabricEvent] = []

    def __call__(self, ev: FabricEvent) -> None:
        self.events.append(ev)

    def on_event(self, ev: FabricEvent) -> None:
        self.events.append(ev)
