"""Kernel event integrity helpers.

Provides deterministic fingerprints without changing EventBus behaviour.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from .primitives import DomainEvent


def canonical_payload(payload: Dict[str, Any]) -> str:
    """Return a stable JSON representation for event hashing."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def event_fingerprint(event: DomainEvent) -> str:
    """Create a deterministic integrity fingerprint for an event.

    The fingerprint intentionally excludes random event_id values so identical
    logical events can be compared across replay boundaries.
    """
    material = "|".join(
        (
            event.topic,
            event.correlation_id,
            canonical_payload(event.payload),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class EventIntegrityIndex:
    """Small in-memory duplicate detector for diagnostic use."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def observe(self, event: DomainEvent) -> bool:
        """Return False when the logical event fingerprint was seen before."""
        fingerprint = event_fingerprint(event)
        if fingerprint in self._seen:
            return False
        self._seen.add(fingerprint)
        return True

    def size(self) -> int:
        return len(self._seen)
