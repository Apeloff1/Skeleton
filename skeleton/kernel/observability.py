"""Shared observability primitives for structured, correlated, redacted telemetry.

The kernel event bus is the transport. This module supplies a bounded collector
and baseline operational metrics without coupling core runtime code to a logging
vendor or exporting raw sensitive payloads.
"""
from __future__ import annotations

import re
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from skeleton.kernel.events import DomainEvent, EventBus

_REDACTED = "[REDACTED]"
_TRUNCATED = "[TRUNCATED]"
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set_cookie",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "credential",
    "credentials",
}
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password|authorization)"
    r"\b\s*[:=]\s*([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def _normalize_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def redact_text(value: str) -> str:
    """Redact common credential shapes without otherwise rewriting log text."""
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    return _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={_REDACTED}", value
    )


def redact_payload(value: Any, *, max_depth: int = 8) -> Any:
    """Return a telemetry-safe copy of nested payload data.

    Keys commonly used for credentials are removed by value, strings are
    scrubbed for common inline secret assignments/Bearer tokens, and excessive
    nesting is bounded so attacker-controlled payloads cannot recurse forever.
    """
    if isinstance(max_depth, bool) or not isinstance(max_depth, int):
        raise TypeError("max_depth must be an integer")
    if max_depth < 1:
        raise ValueError("max_depth must be at least 1")

    def visit(item: Any, depth: int, key: object | None = None) -> Any:
        if key is not None and _normalize_key(key) in _SENSITIVE_KEYS:
            return _REDACTED
        if depth >= max_depth:
            return _TRUNCATED
        if isinstance(item, str):
            return redact_text(item)
        if isinstance(item, Mapping):
            return {
                str(child_key): visit(child_value, depth + 1, child_key)
                for child_key, child_value in item.items()
            }
        if isinstance(item, tuple):
            return tuple(visit(child, depth + 1) for child in item)
        if isinstance(item, list):
            return [visit(child, depth + 1) for child in item]
        if isinstance(item, set):
            return sorted((visit(child, depth + 1) for child in item), key=repr)
        return item

    return visit(value, 0)


@dataclass(frozen=True, slots=True)
class ObservedEvent:
    topic: str
    payload: Mapping[str, Any]
    correlation_id: str
    timestamp: float


class OperationalMetrics:
    """Small in-process baseline metrics derived from structured events."""

    def __init__(self) -> None:
        self.events_total = 0
        self.failures_total = 0
        self.retries_total = 0
        self.rate_limits_total = 0
        self._topics: Counter[str] = Counter()
        self._latency_count = 0
        self._latency_total_ms = 0.0
        self._latency_max_ms = 0.0
        self._queue_depth = 0
        self._queue_depth_max = 0
        self._memory_bytes = 0
        self._memory_bytes_max = 0

    def observe(self, event: ObservedEvent) -> None:
        payload = event.payload
        self.events_total += 1
        self._topics[event.topic] += 1

        status = payload.get("status")
        if (
            event.topic.endswith(".failed")
            or status in {"failed", "error"}
            or (isinstance(status, int) and status >= 500)
        ):
            self.failures_total += 1
        if "retry" in event.topic or payload.get("retrying") is True:
            self.retries_total += 1
        if (
            "rate_limit" in event.topic
            or "rate-limit" in event.topic
            or status == 429
        ):
            self.rate_limits_total += 1

        duration = payload.get("duration_ms")
        if (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and duration >= 0
        ):
            duration = float(duration)
            self._latency_count += 1
            self._latency_total_ms += duration
            self._latency_max_ms = max(self._latency_max_ms, duration)

        queue_depth = payload.get("queue_depth")
        if (
            isinstance(queue_depth, int)
            and not isinstance(queue_depth, bool)
            and queue_depth >= 0
        ):
            self._queue_depth = queue_depth
            self._queue_depth_max = max(self._queue_depth_max, queue_depth)

        memory_bytes = payload.get("memory_bytes")
        if (
            isinstance(memory_bytes, int)
            and not isinstance(memory_bytes, bool)
            and memory_bytes >= 0
        ):
            self._memory_bytes = memory_bytes
            self._memory_bytes_max = max(self._memory_bytes_max, memory_bytes)

    def snapshot(self) -> dict[str, Any]:
        latency_avg = (
            self._latency_total_ms / self._latency_count
            if self._latency_count
            else 0.0
        )
        return {
            "events_total": self.events_total,
            "failures_total": self.failures_total,
            "retries_total": self.retries_total,
            "rate_limits_total": self.rate_limits_total,
            "topics": dict(sorted(self._topics.items())),
            "latency_ms": {
                "count": self._latency_count,
                "avg": round(latency_avg, 3),
                "max": round(self._latency_max_ms, 3),
            },
            "queue_depth": {
                "current": self._queue_depth,
                "max": self._queue_depth_max,
            },
            "memory_bytes": {
                "current": self._memory_bytes,
                "max": self._memory_bytes_max,
            },
        }


class StructuredEventCollector:
    """Bounded subscriber that stores redacted events and baseline metrics."""

    def __init__(self, *, max_events: int = 1000) -> None:
        if isinstance(max_events, bool) or not isinstance(max_events, int):
            raise TypeError("max_events must be an integer")
        if max_events < 1:
            raise ValueError("max_events must be at least 1")
        self._events: deque[ObservedEvent] = deque(maxlen=max_events)
        self.metrics = OperationalMetrics()

    def attach(self, bus: EventBus) -> None:
        bus.subscribe("*", self.observe)

    def observe(self, event: DomainEvent) -> None:
        sanitized = redact_payload(event.payload)
        if not isinstance(sanitized, Mapping):
            sanitized = {"value": sanitized}
        observed = ObservedEvent(
            topic=event.topic,
            payload=dict(sanitized),
            correlation_id=redact_text(event.correlation_id),
            timestamp=event.timestamp,
        )
        self._events.append(observed)
        self.metrics.observe(observed)

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
            "metrics": self.metrics.snapshot(),
        }
