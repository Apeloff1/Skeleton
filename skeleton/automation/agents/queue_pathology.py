"""Deterministic queue-pathology reasoning for the AI/swarm control plane.

This turns scheduler incidents (including non-terminal cancellation conflicts) into
bounded, explainable decisions the intelligence layer can consume without teaching
it to treat infrastructure residue as useful work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class QueueDisposition(str, Enum):
    HEALTHY = "healthy"
    CONGESTED = "congested"
    ZOMBIE = "zombie"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class QueueObservation:
    work_id: str
    state: str
    age_seconds: int
    attempts: int = 0
    last_status: int | None = None
    source_exists: bool = True
    authoritative: bool = False


@dataclass(frozen=True, slots=True)
class QueueDecision:
    work_id: str
    disposition: QueueDisposition
    retry: bool
    consume_capacity: bool
    escalate: bool
    reason: str


_RETRYABLE = frozenset({0, 409, 422, 429, 500, 502, 503, 504})


def classify_queue_observation(
    observation: QueueObservation,
    *,
    zombie_after_seconds: int = 900,
    retry_budget: int = 8,
) -> QueueDecision:
    """Classify one queue item fail-closed and without hiding authoritative work."""
    if zombie_after_seconds < 1 or retry_budget < 1:
        raise ValueError("queue pathology thresholds must be positive")
    if observation.age_seconds < 0 or observation.attempts < 0:
        raise ValueError("queue observation counters must be non-negative")

    state = observation.state.lower().strip()
    if state in {"completed", "success", "failed", "cancelled"}:
        return QueueDecision(
            observation.work_id, QueueDisposition.HEALTHY, False, False, False,
            "terminal work does not consume live queue capacity",
        )

    stale = observation.age_seconds >= zombie_after_seconds
    conflict = observation.last_status in _RETRYABLE
    orphaned = not observation.source_exists

    # Never garbage-collect authoritative work merely because it is old.
    if observation.authoritative:
        return QueueDecision(
            observation.work_id,
            QueueDisposition.CONGESTED if stale else QueueDisposition.HEALTHY,
            conflict,
            True,
            stale and observation.attempts >= retry_budget,
            "authoritative work is preserved until terminal evidence exists",
        )

    if stale and orphaned and conflict:
        exhausted = observation.attempts >= retry_budget
        return QueueDecision(
            observation.work_id,
            QueueDisposition.ZOMBIE,
            not exhausted,
            False,
            exhausted,
            "orphaned non-terminal work repeatedly conflicts with scheduler cancellation",
        )

    if conflict:
        return QueueDecision(
            observation.work_id, QueueDisposition.DEFERRED, True, True, False,
            "scheduler conflict is transient until age/source evidence proves pathology",
        )

    if stale:
        return QueueDecision(
            observation.work_id, QueueDisposition.CONGESTED, False, True, False,
            "old live work remains capacity-bearing because zombie evidence is incomplete",
        )

    return QueueDecision(
        observation.work_id, QueueDisposition.HEALTHY, False, True, False,
        "live work is within queue-health thresholds",
    )


def summarize_queue_health(
    observations: Iterable[QueueObservation],
    *,
    zombie_after_seconds: int = 900,
    retry_budget: int = 8,
) -> dict[str, int]:
    """Return AI-friendly capacity counts; zombies are isolated from useful backlog."""
    counts = {item.value: 0 for item in QueueDisposition}
    counts.update({"capacity_bearing": 0, "retryable": 0, "escalations": 0})
    for observation in observations:
        decision = classify_queue_observation(
            observation,
            zombie_after_seconds=zombie_after_seconds,
            retry_budget=retry_budget,
        )
        counts[decision.disposition.value] += 1
        counts["capacity_bearing"] += int(decision.consume_capacity)
        counts["retryable"] += int(decision.retry)
        counts["escalations"] += int(decision.escalate)
    return counts
