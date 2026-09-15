"""Shared observability contract for correlation, safe events, and baseline metrics.

The contract is intentionally provider-neutral.  Core subsystems bind a
:class:`CorrelationContext`, enrich it as work crosses agent/tool boundaries,
and emit structured events through one redacting sink.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from threading import RLock
from typing import Any, Callable, Dict, Iterator, Mapping, Optional

from skeleton.observability.metrics import MetricsCollector

_REDACTED = "[REDACTED]"
_SENSITIVE_PARTS = (
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "cookie",
    "credential",
    "private_key",
    "access_key",
)


@dataclass(frozen=True)
class CorrelationContext:
    """Identifiers that must survive subsystem boundaries."""

    request_id: str
    run_id: str
    trace_id: str
    agent_id: Optional[str] = None
    tool_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        *,
        request_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> "CorrelationContext":
        return cls(
            request_id=_clean_id(request_id) or _new_id(),
            run_id=_clean_id(run_id) or _new_id(),
            trace_id=_clean_id(trace_id) or _new_id(),
        )

    def enrich(
        self,
        *,
        agent_id: Optional[str] = None,
        tool_id: Optional[str] = None,
    ) -> "CorrelationContext":
        return replace(
            self,
            agent_id=self.agent_id if agent_id is None else _clean_id(agent_id),
            tool_id=self.tool_id if tool_id is None else _clean_id(tool_id),
        )

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "tool_id": self.tool_id,
        }


_CURRENT: ContextVar[Optional[CorrelationContext]] = ContextVar(
    "skeleton_observability_context", default=None
)


def current_context() -> Optional[CorrelationContext]:
    return _CURRENT.get()


@contextmanager
def bind_context(context: CorrelationContext) -> Iterator[CorrelationContext]:
    """Bind correlation to the current sync/async execution context."""

    token: Token = _CURRENT.set(context)
    try:
        yield context
    finally:
        _CURRENT.reset(token)


def annotate_context(
    *, agent_id: Optional[str] = None, tool_id: Optional[str] = None
) -> Optional[CorrelationContext]:
    """Persist boundary identifiers for the remainder of the bound request."""

    context = current_context()
    if context is None:
        return None
    updated = context.enrich(agent_id=agent_id, tool_id=tool_id)
    _CURRENT.set(updated)
    return updated


def redact(value: Any) -> Any:
    """Recursively redact telemetry fields whose names imply credentials."""

    if isinstance(value, Mapping):
        result: Dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower().replace("-", "_")
            result[key] = _REDACTED if _is_sensitive(key_text) else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def _is_sensitive(key: str) -> bool:
    return any(part in key for part in _SENSITIVE_PARTS)


def _clean_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned[:128] if cleaned else None


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


class ObservabilityContract:
    """Structured events plus the baseline operational metric family.

    Baseline metrics emitted by core operations:
    ``skeleton_operations_total``, ``skeleton_operation_latency_ms``,
    ``skeleton_failures_total``, ``skeleton_retries_total``,
    ``skeleton_rate_limits_total``, ``skeleton_queue_depth``, and
    ``skeleton_resource_usage``.
    """

    def __init__(
        self,
        metrics: Optional[MetricsCollector] = None,
        sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.metrics = metrics or MetricsCollector()
        self._sink = sink
        self._events: list[Dict[str, Any]] = []
        self._lock = RLock()

    def emit(
        self,
        event: str,
        *,
        component: str,
        status: str = "ok",
        duration_ms: Optional[float] = None,
        retry: bool = False,
        rate_limited: bool = False,
        queue_depth: Optional[float] = None,
        resource_usage: Optional[float] = None,
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = current_context()
        labels = {"component": component, "event": event, "status": status}
        self.metrics.increment("skeleton_operations_total", labels=labels)
        if duration_ms is not None:
            self.metrics.histogram(
                "skeleton_operation_latency_ms",
                float(duration_ms),
                labels={"component": component, "event": event},
            )
        if status != "ok":
            self.metrics.increment(
                "skeleton_failures_total", labels={"component": component, "event": event}
            )
        if retry:
            self.metrics.increment(
                "skeleton_retries_total", labels={"component": component, "event": event}
            )
        if rate_limited:
            self.metrics.increment(
                "skeleton_rate_limits_total", labels={"component": component, "event": event}
            )
        if queue_depth is not None:
            self.metrics.gauge(
                "skeleton_queue_depth", float(queue_depth), labels={"component": component}
            )
        if resource_usage is not None:
            self.metrics.gauge(
                "skeleton_resource_usage", float(resource_usage), labels={"component": component}
            )

        record: Dict[str, Any] = {
            "timestamp_ns": time.time_ns(),
            "event": event,
            "component": component,
            "status": status,
            "correlation": context.to_dict() if context else {},
            "attrs": redact(dict(attrs or {})),
        }
        if duration_ms is not None:
            record["duration_ms"] = round(float(duration_ms), 6)
        with self._lock:
            self._events.append(record)
        if self._sink is not None:
            self._sink(record)
        return record

    @contextmanager
    def operation(
        self, event: str, *, component: str, attrs: Optional[Mapping[str, Any]] = None
    ) -> Iterator[None]:
        started = time.perf_counter_ns()
        try:
            yield
        except Exception:
            self.emit(
                event,
                component=component,
                status="error",
                duration_ms=(time.perf_counter_ns() - started) / 1e6,
                attrs=attrs,
            )
            raise
        else:
            self.emit(
                event,
                component=component,
                duration_ms=(time.perf_counter_ns() - started) / 1e6,
                attrs=attrs,
            )

    def events(self) -> list[Dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


_DEFAULT = ObservabilityContract()


def get_observability() -> ObservabilityContract:
    return _DEFAULT


def reset_observability() -> ObservabilityContract:
    """Reset the process-local default; intended for deterministic tests."""

    global _DEFAULT
    _DEFAULT = ObservabilityContract()
    return _DEFAULT
