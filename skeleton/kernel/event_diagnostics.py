"""Kernel event diagnostics helpers.

Provides a non-invasive bridge between EventBus events and integrity tracking.
The bridge intentionally avoids changing EventBus dispatch semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .event_integrity import EventIntegrityIndex, event_fingerprint
from .primitives import DomainEvent


@dataclass(frozen=True)
class EventDiagnostic:
    event_id: str
    topic: str
    fingerprint: str
    duplicate: bool


class EventDiagnostics:
    """Diagnostic observer for event integrity checks."""

    def __init__(self, index: Optional[EventIntegrityIndex] = None) -> None:
        self._index = index or EventIntegrityIndex()

    def inspect(self, event: DomainEvent) -> EventDiagnostic:
        return EventDiagnostic(
            event_id=event.event_id,
            topic=event.topic,
            fingerprint=event_fingerprint(event),
            duplicate=not self._index.observe(event),
        )

    def seen_count(self) -> int:
        return self._index.size()
