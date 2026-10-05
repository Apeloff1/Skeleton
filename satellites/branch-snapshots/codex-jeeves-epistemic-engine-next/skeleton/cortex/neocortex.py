"""
Skeleton Cortex — Observability and control surface

Provides:
- JeevesCortex: Central observability hub that monitors the whole event bus
- CortexSnapshot: Point-in-time system state capture
- ControlSurface: Runtime control and intervention
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class CortexSnapshot:
    """Point-in-time capture of system state."""
    timestamp: float
    event_counts: Dict[str, int] = field(default_factory=dict)
    handle_status: Dict[str, str] = field(default_factory=dict)
    bus_stats: Dict[str, Any] = field(default_factory=dict)
    invariant_violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_counts": self.event_counts,
            "handle_status": self.handle_status,
            "bus_stats": self.bus_stats,
            "invariant_violations": self.invariant_violations,
        }


class JeevesCortex:
    """Observability hub that monitors the entire Skeleton system."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._event_log: List[DomainEvent] = []
        self._event_counts: Dict[str, int] = {}
        self._max_log_size = 10000
        
        if bus:
            bus.subscribe("*", self._on_event)

    def _on_event(self, event: DomainEvent) -> None:
        """Capture all events for observability."""
        self._event_log.append(event)
        self._event_counts[event.topic] = self._event_counts.get(event.topic, 0) + 1
        
        # Trim log if too large
        if len(self._event_log) > self._max_log_size:
            self._event_log = self._event_log[-self._max_log_size // 2:]

    def snapshot(self) -> CortexSnapshot:
        """Capture current system state."""
        bus_stats = self._bus.stats() if self._bus else {}
        
        return CortexSnapshot(
            timestamp=time.time(),
            event_counts=dict(self._event_counts),
            bus_stats=bus_stats,
        )

    def recent_events(self, topic: Optional[str] = None, n: int = 50) -> List[Dict[str, Any]]:
        """Get recent events, optionally filtered by topic."""
        events = self._event_log
        if topic:
            events = [e for e in events if e.topic == topic or e.topic.startswith(topic + ".")]
        
        return [
            {
                "topic": e.topic,
                "timestamp": e.timestamp,
                "correlation_id": e.correlation_id,
                "payload_keys": list(e.payload.keys()),
            }
            for e in events[-n:]
        ]

    def event_rate(self, topic: str, window_seconds: float = 60.0) -> float:
        """Calculate event rate for a topic in the recent window."""
        cutoff = time.time() - window_seconds
        recent = [e for e in self._event_log if e.topic == topic and e.timestamp > cutoff]
        return len(recent) / window_seconds if window_seconds > 0 else 0

    def stats(self) -> Dict[str, Any]:
        return {
            "events_captured": len(self._event_log),
            "topics_observed": len(self._event_counts),
            "top_topics": sorted(self._event_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        }


class ControlSurface:
    """Runtime control and intervention surface."""

    def __init__(self, cortex: JeevesCortex, bus: Optional[EventBus] = None):
        self._cortex = cortex
        self._bus = bus
        self._interventions: List[Dict[str, Any]] = []

    def pause_topic(self, topic: str) -> None:
        """Signal to pause processing of a topic."""
        if self._bus:
            self._bus.emit("control.pause", {"topic": topic})
        self._interventions.append({"action": "pause", "topic": topic, "time": time.time()})

    def resume_topic(self, topic: str) -> None:
        """Signal to resume processing of a topic."""
        if self._bus:
            self._bus.emit("control.resume", {"topic": topic})
        self._interventions.append({"action": "resume", "topic": topic, "time": time.time()})

    def inject_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Inject a synthetic event into the bus."""
        if self._bus:
            self._bus.publish(DomainEvent(topic=topic, payload=payload))
        self._interventions.append({"action": "inject", "topic": topic, "time": time.time()})

    def stats(self) -> Dict[str, Any]:
        return {"interventions": len(self._interventions)}
