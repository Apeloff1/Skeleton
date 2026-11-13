"""Process hooks for structured logs, traces, and counters.

These wrap the existing observability types so call sites share one shape.
They do not replace route telemetry or start an OpenTelemetry exporter.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from skeleton.observability.distributed_tracing import Span, Tracer
from skeleton.observability.logging import LogEvent, StructuredLogger


def log_event(
    level: str,
    message: str,
    *,
    logger: StructuredLogger | None = None,
    **context: Any,
) -> LogEvent:
    """Write one redacted structured event."""

    active = logger or StructuredLogger()
    return active.log(level, message, **context)


@contextmanager
def trace_span(
    subsystem: str,
    name: str,
    *,
    tracer: Tracer | None = None,
    **tags: Any,
) -> Iterator[Span]:
    """Open a span and finish it on the way out, including on failure."""

    active = tracer or Tracer(subsystem)
    span = active.start_span(name, tags=dict(tags) if tags else None)
    try:
        yield span
    except Exception as exc:
        active.finish_span(span, tags={"error.type": type(exc).__name__})
        raise
    else:
        active.finish_span(span)


class MetricHook:
    """In-process counters. Snapshots are plain dicts with no secret keys."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def increment(self, name: str, value: int = 1) -> None:
        if not isinstance(name, str) or not name or name != name.strip():
            raise ValueError("metric name must be non-empty normalized text")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("metric increment must be a positive integer")
        self._counts[name] = self._counts.get(name, 0) + value

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)


__all__ = ["MetricHook", "log_event", "trace_span"]
