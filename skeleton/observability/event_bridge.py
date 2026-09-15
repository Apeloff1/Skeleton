"""Bridge kernel DomainEvents into the canonical observability package."""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from weakref import WeakSet

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.observability.metrics_registry import MetricsRegistry
from skeleton.observability.redaction import redact_payload, redact_text


@dataclass(frozen=True, slots=True)
class ObservedEvent:
    topic: str
    payload: Mapping[str, Any]
    correlation_id: str
    timestamp: float


class EventMetricsBridge:
    """Bounded, redacted event recorder backed by the existing metrics registry."""

    def __init__(
        self,
        *,
        registry: MetricsRegistry | None = None,
        max_events: int = 1000,
    ) -> None:
        if isinstance(max_events, bool) or not isinstance(max_events, int):
            raise TypeError("max_events must be an integer")
        if max_events < 1:
            raise ValueError("max_events must be at least 1")
        self.registry = registry or MetricsRegistry()
        self._events: deque[ObservedEvent] = deque(maxlen=max_events)
        self._attached_buses: WeakSet[EventBus] = WeakSet()

    def attach(self, bus: EventBus) -> None:
        """Attach to a bus once; repeated attachment must not double-count events."""
        if bus in self._attached_buses:
            return
        bus.subscribe("*", self.observe)
        self._attached_buses.add(bus)

    def observe(self, event: DomainEvent) -> None:
        payload = redact_payload(event.payload)
        if not isinstance(payload, Mapping):
            payload = {"value": payload}
        observed = ObservedEvent(
            topic=redact_text(event.topic),
            payload=dict(payload),
            correlation_id=redact_text(event.correlation_id),
            timestamp=event.timestamp,
        )
        self._events.append(observed)
        self._update_metrics(observed)

    def _update_metrics(self, event: ObservedEvent) -> None:
        payload = event.payload
        labels = {"topic": event.topic}
        self.registry.counter("observability.events_total", labels=labels)

        status = payload.get("status")
        failed_status = isinstance(status, str) and status.lower() in {
            "failed",
            "error",
        }
        failed_code = (
            isinstance(status, int)
            and not isinstance(status, bool)
            and status >= 500
        )
        if event.topic.endswith(".failed") or failed_status or failed_code:
            self.registry.counter("observability.failures_total", labels=labels)
        if "retry" in event.topic or payload.get("retrying") is True:
            self.registry.counter("observability.retries_total", labels=labels)
        if "rate_limit" in event.topic or "rate-limit" in event.topic or status == 429:
            self.registry.counter("observability.rate_limits_total", labels=labels)

        duration = payload.get("duration_ms")
        if (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and duration >= 0
        ):
            self.registry.observe(
                "observability.latency_ms",
                float(duration),
                labels=labels,
            )

        queue_depth = payload.get("queue_depth")
        if (
            isinstance(queue_depth, int)
            and not isinstance(queue_depth, bool)
            and queue_depth >= 0
        ):
            self.registry.gauge("observability.queue_depth", float(queue_depth))

        memory_bytes = payload.get("memory_bytes")
        if (
            isinstance(memory_bytes, int)
            and not isinstance(memory_bytes, bool)
            and memory_bytes >= 0
        ):
            self.registry.gauge("observability.memory_bytes", float(memory_bytes))

    def events(self) -> tuple[ObservedEvent, ...]:
        return tuple(self._events)

    def snapshot(self) -> dict[str, Any]:
        return {
            "events": [
                {
                    "topic": event.topic,
                    "payload": dict(event.payload),
                    "correlation_id": event.correlation_id,
                    "timestamp": event.timestamp,
                }
                for event in self._events
            ],
            "metrics": self.registry.rollup(),
        }
