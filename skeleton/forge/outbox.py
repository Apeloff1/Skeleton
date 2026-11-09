"""Forge materialise outbox — journal-first durability for materialisations.

Ported from ``backend/zaibatsu/outbox.py`` durability law into skeleton/forge
style. The law: intent is journaled *before* the materialisation is admitted
anywhere observable as durable, and a reconciler confirms each journal entry
into a sink. A crash between journal and sink leaves an unconfirmed row
that reconcile() replays — a decided materialisation can never exist nowhere
durable.

When the outbox is full it backpressures (raises ``OutboxFull``), it never
drops. Sync-first to match ``Forge.materialise``; an optional async reconciler
is provided for callers that already run an event loop.

Callers may inject an outbox via ``Forge(..., outbox=...)`` or wire a listen-
style helper with ``bind_materialise_outbox(bus, outbox)`` without touching
verify / repair surfaces.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from skeleton.kernel.events import DomainEvent, EventBus

COLLECTION = "forge_materialisations"


class OutboxFull(Exception):
    """Durability is backpressured, not dropped. Caller sees this."""


@dataclass
class MaterialiseIntent:
    """One journaled materialisation awaiting (or having received) sink confirm."""

    seq: int
    document: dict[str, Any]
    journaled_at: float = field(default_factory=time.time)
    confirmed: bool = False
    attempts: int = 0
    dead: bool = False
    last_error: str = ""

    @property
    def blueprint_id(self) -> str:
        return str(self.document.get("blueprint_id") or "")


Sink = Callable[[dict[str, Any]], None]


class MemorySink:
    """In-process durable sink for tests and single-process callers."""

    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def __call__(self, document: dict[str, Any]) -> None:
        self.documents.append(dict(document))


class MaterialiseOutbox:
    """Bounded journal + reconciler for forge materialisations.

    ``sink`` performs the durable write (file, DB, MemorySink, …). Journal
    capacity is counted in *unconfirmed* intents; confirmed rows are drained
    from the hot pending deque after each reconcile.
    """

    def __init__(self, sink: Sink | None = None, *, cap: int = 4096) -> None:
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ValueError("outbox cap must be a positive integer")
        self._sink: Sink = sink if sink is not None else MemorySink()
        self._cap = cap
        self._pending: deque[MaterialiseIntent] = deque()
        self._seq = 0
        self._lock = threading.Lock()
        self.journaled_total = 0
        self.confirmed_total = 0

    def journal(self, document: dict[str, Any]) -> int:
        """Append a durable intent. Raises ``OutboxFull`` when backpressured."""
        if not isinstance(document, dict):
            raise TypeError("outbox journal document must be a dict")
        with self._lock:
            unconfirmed = sum(1 for i in self._pending if not i.confirmed)
            if unconfirmed >= self._cap:
                raise OutboxFull("outbox at capacity — write is refused, not lost")
            self._seq += 1
            payload = dict(document)
            payload.setdefault("collection", COLLECTION)
            payload.setdefault("seq", self._seq)
            self._pending.append(MaterialiseIntent(seq=self._seq, document=payload))
            self.journaled_total += 1
            return self._seq

    def append_materialisation(
        self,
        *,
        blueprint_id: str,
        components: int,
        wires: int,
        era: str,
        target: str,
        name: str = "",
        extra: dict[str, Any] | None = None,
    ) -> int:
        """Journal a forge.blueprint.materialised-shaped record."""
        if not isinstance(blueprint_id, str) or not blueprint_id.strip():
            raise ValueError("blueprint_id is required")
        if not isinstance(era, str) or not era.strip() or not isinstance(target, str) or not target.strip():
            raise ValueError("era and target are required")
        if isinstance(components, bool) or not isinstance(components, int) or components < 0:
            raise ValueError("components must be a non-negative integer")
        if isinstance(wires, bool) or not isinstance(wires, int) or wires < 0:
            raise ValueError("wires must be a non-negative integer")
        document: dict[str, Any] = {
            "kind": "forge.blueprint.materialised",
            "blueprint_id": blueprint_id,
            "name": name,
            "components": components,
            "wires": wires,
            "era": era,
            "target": target,
            "ts": time.time(),
        }
        if extra:
            document["extra"] = dict(extra)
        return self.journal(document)

    def reconcile(self) -> int:
        """Confirm everything unconfirmed, oldest first. Returns confirm count."""
        done = 0
        with self._lock:
            for intent in self._pending:
                if intent.confirmed:
                    continue
                if intent.dead:
                    continue
                try:
                    self._sink(dict(intent.document))
                    intent.confirmed = True
                    intent.last_error = ""
                    done += 1
                    self.confirmed_total += 1
                except Exception as exc:
                    intent.attempts += 1
                    intent.last_error = type(exc).__name__
                    if intent.attempts >= 8:
                        intent.dead = True
            while self._pending and self._pending[0].confirmed:
                self._pending.popleft()
        return done

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for i in self._pending if not i.confirmed)

    def pending(self) -> list[MaterialiseIntent]:
        """Snapshot of unconfirmed intents, oldest first."""
        with self._lock:
            return [i for i in self._pending if not i.confirmed]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            pending = sum(1 for i in self._pending if not i.confirmed)
            return {
                "cap": self._cap,
                "pending": pending,
                "journaled_total": self.journaled_total,
                "confirmed_total": self.confirmed_total,
                "seq": self._seq,
            }


def bind_materialise_outbox(bus: EventBus, outbox: MaterialiseOutbox) -> Callable[[], None]:
    """Listen-style helper: append on ``forge.blueprint.materialised``.

    Prefer this when you cannot or should not inject ``outbox=`` into Forge
    (e.g. Lana's e2e spine owns Forge construction). Returns unsubscribe.
    """

    def _handler(event: DomainEvent) -> None:
        payload = event.payload or {}
        outbox.append_materialisation(
            blueprint_id=payload.get("blueprint_id"),
            components=payload.get("components"),
            wires=payload.get("wires"),
            era=payload.get("era"),
            target=payload.get("target"),
            name=payload.get("name") or "",
            extra={"source": "bus", "correlation_id": event.correlation_id},
        )

    return bus.subscribe(
        "forge.blueprint.materialised",
        _handler,
        name="forge.materialise.outbox",
    )


async def run_reconciler(outbox: MaterialiseOutbox, interval_secs: float = 5.0) -> None:
    """Optional async reconciler. Never retires; it only waits."""
    import asyncio

    while True:
        await asyncio.sleep(interval_secs)
        outbox.reconcile()
