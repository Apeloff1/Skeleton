"""Distributed tracing — cross-subsystem span collection and correlation.

Provides OpenTelemetry-style spans with context propagation across
all Skeleton subsystems. Supports sampling, baggage, and export hooks.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    sampled: bool = True
    baggage: Dict[str, str] = field(default_factory=dict)

    def fork(self, sampled: Optional[bool] = None) -> "SpanContext":
        return SpanContext(
            trace_id=self.trace_id,
            span_id=_new_id(),
            parent_id=self.span_id,
            sampled=sampled if sampled is not None else self.sampled,
            baggage=dict(self.baggage),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "sampled": self.sampled,
            "baggage": self.baggage,
        }


@dataclass
class Span:
    name: str
    context: SpanContext
    start_ns: float
    end_ns: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    children: List["Span"] = field(default_factory=list)

    def finish(self, tags: Optional[Dict[str, Any]] = None) -> None:
        self.end_ns = time.time_ns()
        if tags:
            self.tags.update(tags)

    def add_event(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> None:
        self.events.append({"name": name, "timestamp_ns": time.time_ns(), "attrs": attrs or {}})

    def duration_ms(self) -> float:
        end = self.end_ns or time.time_ns()
        return (end - self.start_ns) / 1e6

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "context": self.context.to_dict(),
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "duration_ms": self.duration_ms(),
            "tags": self.tags,
            "events": self.events,
            "children": [c.to_dict() for c in self.children],
        }


class Tracer:
    """Per-subsystem tracer with configurable sampling."""

    def __init__(self, subsystem: str, sample_rate: float = 1.0):
        self.subsystem = subsystem
        self.sample_rate = max(0.0, min(1.0, sample_rate))
        self._active: List[Span] = []
        self._finished: List[Span] = []
        self._export_hooks: List[Callable[[Span], None]] = []

    def start_span(self, name: str, parent: Optional[SpanContext] = None, tags: Optional[Dict[str, Any]] = None) -> Span:
        sampled = parent.sampled if parent else (self.sample_rate >= 1.0 or (self.sample_rate > 0 and (uuid.uuid4().int % 10000) < self.sample_rate * 10000))
        ctx = parent.fork(sampled=sampled) if parent else SpanContext(trace_id=_new_id(), span_id=_new_id(), sampled=sampled)
        span = Span(name=name, context=ctx, start_ns=time.time_ns(), tags=tags or {})
        if self._active:
            self._active[-1].children.append(span)
        self._active.append(span)
        return span

    def finish_span(self, span: Span, tags: Optional[Dict[str, Any]] = None) -> None:
        span.finish(tags)
        if span in self._active:
            self._active.remove(span)
        self._finished.append(span)
        for hook in self._export_hooks:
            try:
                hook(span)
            except Exception:
                pass

    def current_context(self) -> Optional[SpanContext]:
        if self._active:
            return self._active[-1].context
        return None

    def inject_context(self, carrier: Dict[str, str]) -> None:
        ctx = self.current_context()
        if ctx:
            carrier["skeleton-trace-id"] = ctx.trace_id
            carrier["skeleton-span-id"] = ctx.span_id
            carrier["skeleton-sampled"] = "1" if ctx.sampled else "0"
            for k, v in ctx.baggage.items():
                carrier[f"skeleton-baggage-{k}"] = v

    def extract_context(self, carrier: Dict[str, str]) -> Optional[SpanContext]:
        tid = carrier.get("skeleton-trace-id")
        sid = carrier.get("skeleton-span-id")
        if not tid or not sid:
            return None
        sampled = carrier.get("skeleton-sampled", "1") == "1"
        baggage = {k[len("skeleton-baggage-"):]: v for k, v in carrier.items() if k.startswith("skeleton-baggage-")}
        return SpanContext(trace_id=tid, span_id=sid, sampled=sampled, baggage=baggage)

    def add_export_hook(self, hook: Callable[[Span], None]) -> None:
        self._export_hooks.append(hook)

    def flush(self) -> List[Dict[str, Any]]:
        out = [s.to_dict() for s in self._finished]
        self._finished.clear()
        return out

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "tracer-card",
            "subsystem": self.subsystem,
            "sample_rate": self.sample_rate,
            "active_spans": len(self._active),
            "finished_spans": len(self._finished),
            "export_hooks": len(self._export_hooks),
        }


def _new_id() -> str:
    return uuid.uuid4().hex[:16]
