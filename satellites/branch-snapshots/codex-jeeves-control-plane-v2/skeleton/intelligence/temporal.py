"""Temporal Reasoning — split from the intelligence monolith (v16.2)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus

# =============================================================================
# 1. TEMPORAL REASONING
# =============================================================================

@dataclass
class TemporalEvent:
    """An event with temporal anchoring."""
    event_id: str
    description: str
    timestamp: float
    duration: Optional[float] = None
    uncertainty: float = 0.0  # Temporal uncertainty in seconds
    relations: Dict[str, str] = field(default_factory=dict)  # event_id -> relation

    def before(self, other: "TemporalEvent") -> bool:
        """Is this event before another (with uncertainty)?"""
        return self.timestamp + self.uncertainty < other.timestamp - other.uncertainty

    def after(self, other: "TemporalEvent") -> bool:
        return other.before(self)

    def overlaps(self, other: "TemporalEvent") -> bool:
        if self.duration is None or other.duration is None:
            return False
        return (
            self.timestamp < other.timestamp + other.duration
            and other.timestamp < self.timestamp + self.duration
        )


class TemporalReasoner:
    """
    Time-aware inference engine.
    Features:
      - Chronology resolution: order events with partial information
      - Future-state prediction: extrapolate from temporal patterns
      - Temporal logic: Allen algebra relations (before, meets, overlaps, etc.)
      - Uncertainty propagation: confidence intervals on temporal queries
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._events: Dict[str, TemporalEvent] = {}
        self._patterns: List[List[str]] = []  # Sequences of event ids
        self._bus = bus

    def add_event(self, event: TemporalEvent) -> None:
        self._events[event.event_id] = event
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="temporal.event.added",
                    payload={
                        "event_id": event.event_id,
                        "timestamp": event.timestamp,
                        "description": event.description,
                    },
                    correlation_id=f"temp_{event.event_id}",
                )
            )

    def resolve_chronology(self, event_ids: List[str]) -> List[TemporalEvent]:
        """
        Resolve chronological order given partial temporal information.
        Uses topological sort with uncertainty-aware comparison.
        """
        events = [self._events[eid] for eid in event_ids if eid in self._events]
        # Sort by timestamp with uncertainty tie-breaking
        return sorted(events, key=lambda e: (e.timestamp, -e.uncertainty))

    def predict_next(
        self,
        sequence: List[str],
        *,
        horizon: float = 3600,  # seconds
        confidence_threshold: float = 0.7,
    ) -> List[Tuple[str, float]]:
        """
        Predict next events based on pattern matching in history.
        Returns list of (event_id, confidence) sorted by confidence.
        """
        if len(sequence) < 2:
            return []

        # Find matching pattern suffixes
        predictions: Dict[str, List[float]] = {}
        for pattern in self._patterns:
            if len(pattern) <= len(sequence):
                continue
            # Check if sequence matches pattern prefix
            if pattern[:len(sequence)] == sequence:
                next_event = pattern[len(sequence)]
                # Compute confidence based on pattern frequency and recency
                confidence = 0.5 + 0.5 * (len(pattern) / (len(pattern) + 10))
                predictions.setdefault(next_event, []).append(confidence)

        # Average confidences
        result = [
            (eid, sum(confs) / len(confs))
            for eid, confs in predictions.items()
            if sum(confs) / len(confs) >= confidence_threshold
        ]
        return sorted(result, key=lambda x: x[1], reverse=True)

    def allen_relation(self, a: TemporalEvent, b: TemporalEvent) -> str:
        """
        Determine Allen algebra relation between two intervals.
        Returns one of: before, meets, overlaps, starts, during, finishes,
        equal, after, met-by, overlapped-by, started-by, contains, finished-by.
        """
        if a.duration is None or b.duration is None:
            # Point events: use simple before/after/equal
            if a.timestamp < b.timestamp:
                return "before"
            elif a.timestamp > b.timestamp:
                return "after"
            else:
                return "equal"

        a_start, a_end = a.timestamp, a.timestamp + a.duration
        b_start, b_end = b.timestamp, b.timestamp + b.duration

        if a_end < b_start:
            return "before"
        elif a_end == b_start:
            return "meets"
        elif a_start < b_start and a_end > b_start and a_end < b_end:
            return "overlaps"
        elif a_start == b_start and a_end < b_end:
            return "starts"
        elif a_start > b_start and a_end < b_end:
            return "during"
        elif a_start > b_start and a_end == b_end:
            return "finishes"
        elif a_start == b_start and a_end == b_end:
            return "equal"
        elif a_start > b_end:
            return "after"
        elif a_start == b_end:
            return "met-by"
        elif b_start < a_start and b_end > a_start and b_end < a_end:
            return "overlapped-by"
        elif b_start == a_start and b_end > a_end:
            return "started-by"
        elif b_start < a_start and b_end > a_end:
            return "contains"
        elif b_start < a_start and b_end == a_end:
            return "finished-by"
        else:
            return "unknown"

    def query_temporal(
        self,
        query: str,
        *,
        time_window: Optional[Tuple[float, float]] = None,
    ) -> List[TemporalEvent]:
        """
        Query events by temporal constraints.
        """
        results = []
        for event in self._events.values():
            if time_window:
                if not (time_window[0] <= event.timestamp <= time_window[1]):
                    continue
            # Simple text matching for now
            if query.lower() in event.description.lower():
                results.append(event)
        return sorted(results, key=lambda e: e.timestamp)

    def learn_pattern(self, sequence: List[str]) -> None:
        """Learn a temporal pattern from an observed sequence."""
        if len(sequence) >= 2:
            self._patterns.append(sequence)
            if self._bus:
                self._bus.publish(
                    DomainEvent(
                        topic="temporal.pattern.learned",
                        payload={"sequence": sequence, "length": len(sequence)},
                        correlation_id=f"pattern_{hashlib.sha256(str(sequence).encode()).hexdigest()[:12]}",
                    )
                )
