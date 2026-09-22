"""Correlation and span tracing for the kernel event fabric.

When an event crosses agents, pipelines, and the vault, a single request
fans out into dozens of bus messages. Without a propagated trace context
there is no way to answer "what happened because of X?" — the merkle log
proves *that* things happened, not *why* they belong together.

- :class:`TraceContext` — immutable (trace_id, span_id, parent_span_id)
  triple carried in event envelopes; ``child()`` forks the next span.
  Ids come from the kernel's id generator conventions, zero deps.
- :class:`Span` — a timed, named operation bound to a context, with
  attributes and a status; ``finish()`` records duration.
- :class:`SpanRecorder` — bounded in-memory sink with per-trace query
  and slow-span reporting. Exporters subscribe to the same interface.

W3C traceparent-style propagation, but kept dependency-free and local.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from .errors import KernelError


class TraceError(KernelError):
    code = "KRN.TRACE"


class SpanStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    sampled: bool = True

    @classmethod
    def root(cls) -> "TraceContext":
        return cls(trace_id=_new_id(), span_id=_new_id())

    def child(self) -> "TraceContext":
        """Fork a child span context — the only way spans link up."""
        return cls(trace_id=self.trace_id, span_id=_new_id(),
                   parent_span_id=self.span_id, sampled=self.sampled)

    def to_headers(self) -> Dict[str, str]:
        return {
            "x-trace-id": self.trace_id,
            "x-span-id": self.span_id,
            "x-parent-span-id": self.parent_span_id or "",
            "x-trace-sampled": "1" if self.sampled else "0",
        }

    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> "TraceContext":
        try:
            return cls(
                trace_id=headers["x-trace-id"],
                span_id=headers["x-span-id"],
                parent_span_id=headers.get("x-parent-span-id") or None,
                sampled=headers.get("x-trace-sampled", "1") == "1",
            )
        except KeyError as exc:
            raise TraceError("malformed trace headers",
                             context={"missing": str(exc)}) from exc


@dataclass
class Span:
    name: str
    context: TraceContext
    started_at: float
    finished_at: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    attributes: Dict[str, object] = field(default_factory=dict)

    @property
    def duration_s(self) -> Optional[float]:
        if self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    def finish(self, status: SpanStatus = SpanStatus.OK,
               *, at: Optional[float] = None) -> None:
        self.finished_at = time.time() if at is None else at
        self.status = status

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "trace_id": self.context.trace_id,
            "span_id": self.context.span_id,
            "parent_span_id": self.context.parent_span_id,
            "started_at": self.started_at,
            "duration_s": self.duration_s,
            "status": self.status.value,
            "attributes": dict(self.attributes),
        }


class SpanRecorder:
    """Bounded sink; exporters read through the same query API."""

    def __init__(self, *, max_spans: int = 10_000,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.time
        self._max = max_spans
        self._spans: List[Span] = []
        self._open: Dict[str, Span] = {}

    def start(self, name: str, context: TraceContext,
              **attributes: object) -> Span:
        if not context.sampled:
            span = Span(name, context, self._now(), attributes=dict(attributes))
            return span
        span = Span(name=name, context=context, started_at=self._now(),
                    attributes=dict(attributes))
        self._open[context.span_id] = span
        return span

    def finish(self, span: Span, status: SpanStatus = SpanStatus.OK) -> None:
        if not span.context.sampled:
            return
        span.finish(status, at=self._now())
        self._open.pop(span.context.span_id, None)
        self._spans.append(span)
        if len(self._spans) > self._max:
            del self._spans[: len(self._spans) - self._max]

    def trace(self, trace_id: str) -> Tuple[Span, ...]:
        """All finished spans of one trace, parent-before-child."""
        spans = [s for s in self._spans if s.context.trace_id == trace_id]
        spans.sort(key=lambda s: s.started_at)
        return tuple(spans)

    def slow(self, threshold_s: float, limit: int = 20) -> Tuple[Span, ...]:
        done = [s for s in self._spans
                if s.duration_s is not None and s.duration_s >= threshold_s]
        done.sort(key=lambda s: -(s.duration_s or 0))
        return tuple(done[:limit])

    def orphans(self, older_than_s: float = 60.0) -> Tuple[Span, ...]:
        """Spans started but never finished — leak/crash evidence."""
        now = self._now()
        return tuple(s for s in self._open.values()
                     if now - s.started_at > older_than_s)

    def report(self) -> Dict[str, object]:
        by_trace = defaultdict(int)
        for s in self._spans:
            by_trace[s.context.trace_id] += 1
        return {
            "finished": len(self._spans),
            "open": len(self._open),
            "traces": len(by_trace),
        }
