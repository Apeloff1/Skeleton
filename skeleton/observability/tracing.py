"""Distributed tracing — spans, trace context propagation, in-memory exporter.

Spans form trees via parent ids; a full trace is a correlation handle across
subsystems. The in-memory exporter retains finished spans in a bounded ring and
supports query by trace id, span name, minimum duration, and recency — powering
the `/observability/traces` endpoint without an external collector.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.observability.redaction import redact_payload, redact_text, safe_exception_text

_current_span: contextvars.ContextVar[Optional["Span"]] = contextvars.ContextVar(
    "skeleton_current_span", default=None
)


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "OK"

    def set_attribute(self, key: str, value: Any) -> "Span":
        sanitized = redact_payload({key: value})
        self.attributes[key] = sanitized[key]
        return self

    def add_event(self, name: str, **attrs: Any) -> "Span":
        sanitized = redact_payload(attrs)
        self.events.append(
            {
                "name": redact_text(name),
                "at": time.time(),
                **dict(sanitized),
            }
        )
        return self

    def fail(self, error: BaseException) -> "Span":
        self.status = "ERROR"
        self.attributes["error.type"] = type(error).__name__
        self.attributes["error.message"] = safe_exception_text(error)
        return self

    @property
    def duration_ms(self) -> Optional[float]:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        sanitized_attributes = redact_payload(self.attributes)
        sanitized_events = redact_payload(self.events)
        return {
            "name": redact_text(self.name),
            "trace_id": redact_text(self.trace_id),
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": sanitized_attributes,
            "events": sanitized_events,
        }


class InMemoryExporter:
    def __init__(self, capacity: int = 8192) -> None:
        self._spans: List[Span] = []
        self._capacity = capacity

    def export(self, span: Span) -> None:
        self._spans.append(span)
        if len(self._spans) > self._capacity:
            del self._spans[: len(self._spans) - self._capacity]

    def by_trace(self, trace_id: str) -> List[Span]:
        return [s for s in self._spans if s.trace_id == trace_id]

    def query(
        self,
        name: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        limit: int = 50,
    ) -> List[Span]:
        out = [
            s
            for s in reversed(self._spans)
            if (name is None or s.name == name)
            and (
                min_duration_ms is None
                or (s.duration_ms is not None and s.duration_ms >= min_duration_ms)
            )
        ]
        return out[:limit]


class Tracer:
    def __init__(
        self,
        service_name: str,
        exporter: Optional[InMemoryExporter] = None,
    ) -> None:
        self.service_name = service_name
        self.exporter = exporter or InMemoryExporter()

    def start_span(
        self,
        name: str,
        trace_id: Optional[str] = None,
        **attributes: Any,
    ) -> Span:
        parent = _current_span.get()
        sanitized = redact_payload({"service": self.service_name, **attributes})
        return Span(
            name=redact_text(name),
            trace_id=redact_text(
                trace_id or (parent.trace_id if parent else uuid.uuid4().hex)
            ),
            span_id=uuid.uuid4().hex[:16],
            parent_id=parent.span_id if parent else None,
            attributes=dict(sanitized),
        )

    def __call__(self, name: str, **attributes: Any) -> "SpanContext":
        return SpanContext(self, name, attributes)


class SpanContext:
    """Context manager: sets the current span and exports it best-effort."""

    def __init__(self, tracer: Tracer, name: str, attributes: Dict[str, Any]) -> None:
        self._tracer, self._name, self._attributes = tracer, name, attributes
        self._token: Optional[contextvars.Token] = None
        self.span: Optional[Span] = None

    def __enter__(self) -> Span:
        self.span = self._tracer.start_span(self._name, **self._attributes)
        self._token = _current_span.set(self.span)
        return self.span

    def __exit__(self, exc_type, exc, tb) -> bool:
        assert self.span is not None
        if exc is not None:
            self.span.fail(exc)
        self.span.ended_at = time.time()
        try:
            self._tracer.exporter.export(self.span)
        except Exception:
            pass
        if self._token is not None:
            _current_span.reset(self._token)
        return False
