"""Kernel assurance bridge.

Keeps assurance metadata attached at the event boundary without changing the
existing DomainEvent contract. Consumers can validate enriched events before
state mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from skeleton.kernel.assurance import AssuranceEnvelope
from skeleton.kernel.primitives import DomainEvent


@dataclass(frozen=True)
class AssuranceEventRecord:
    """Validated association between an event and its assurance envelope."""

    event_id: str
    envelope_digest: str
    topic: str


def bind_assurance(event: DomainEvent, envelope: AssuranceEnvelope) -> DomainEvent:
    """Return a derived event carrying assurance metadata.

    The original event object remains immutable. Metadata is copied into the
    payload so existing EventBus subscribers continue to receive DomainEvent.
    """

    payload: Dict[str, Any] = dict(event.payload)
    payload["assurance"] = {
        "state": envelope.state.value,
        "digest": envelope.digest,
        "task_id": envelope.task_id,
        "source": envelope.source,
    }
    return DomainEvent(
        topic=event.topic,
        payload=payload,
        correlation_id=event.correlation_id,
        causation_id=event.event_id,
    )
