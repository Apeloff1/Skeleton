"""Assurance observability bridge.

Keeps assurance decisions observable without coupling telemetry storage
with the validation path.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Any


@dataclass(frozen=True)
class AssuranceObservation:
    event_id: str
    state: str
    task_id: str
    evidence_digest: str
    recorded_at: str
    metadata: Mapping[str, Any]


def observe_assurance_event(
    event_id: str,
    state: str,
    task_id: str,
    evidence_digest: str,
    metadata: Mapping[str, Any] | None = None,
) -> AssuranceObservation:
    if not event_id:
        raise ValueError("event_id required")
    if not task_id:
        raise ValueError("task_id required")
    if not evidence_digest:
        raise ValueError("evidence_digest required")

    return AssuranceObservation(
        event_id=event_id,
        state=state,
        task_id=task_id,
        evidence_digest=evidence_digest,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        metadata=metadata or {},
    )
