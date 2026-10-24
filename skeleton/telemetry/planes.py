"""Per-plane tracing and metrics for the kernel, agents, and API (#121).

Thin adapter over the canonical ``skeleton.observability`` primitives: spans
come from :class:`~skeleton.observability.tracing.Tracer` and metrics from
:class:`~skeleton.observability.metrics_registry.MetricsRegistry`. Nothing here
creates a second plane; every span and series is tagged with the active
correlation id from :mod:`skeleton.observability.correlation` so a request can
be followed API -> agent -> kernel.

Extend-only: no existing route, lifespan, or bus is modified. Callers opt in by
wrapping work in ``plane_span("kernel", "dispatch")`` (or the per-plane
helpers ``kernel_span`` / ``agent_span`` / ``api_span``).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from skeleton.observability.correlation import get_correlation_id
from skeleton.observability.metrics_registry import MetricsRegistry
from skeleton.observability.tracing import InMemoryExporter, Span, Tracer

PLANES = ("kernel", "agents", "api")

CALLS = "telemetry.plane.calls"
ERRORS = "telemetry.plane.errors"
LATENCY_MS = "telemetry.plane.latency_ms"


class PlaneTelemetry:
    """Shared tracer + metrics registry for the three engine planes."""

    def __init__(
        self,
        *,
        service_name: str = "skeleton",
        exporter: Optional[InMemoryExporter] = None,
        registry: Optional[MetricsRegistry] = None,
    ) -> None:
        self.exporter = exporter or InMemoryExporter()
        self.registry = registry or MetricsRegistry()
        self._tracers: Dict[str, Tracer] = {
            plane: Tracer(f"{service_name}.{plane}", exporter=self.exporter)
            for plane in PLANES
        }

    def tracer(self, plane: str) -> Tracer:
        if plane not in self._tracers:
            raise ValueError(f"unknown telemetry plane: {plane!r}; expected one of {PLANES}")
        return self._tracers[plane]

    @contextmanager
    def span(self, plane: str, operation: str, **attributes: Any) -> Iterator[Span]:
        tracer = self.tracer(plane)
        labels = {"plane": plane, "op": operation}
        correlation_id = get_correlation_id()
        attrs: Dict[str, Any] = {"plane": plane, **attributes}
        if correlation_id:
            attrs["correlation_id"] = correlation_id
        started = time.perf_counter()
        self.registry.counter(CALLS, labels=labels)
        try:
            with tracer(f"{plane}.{operation}", **attrs) as span:
                yield span
        except BaseException:
            self.registry.counter(ERRORS, labels=labels)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self.registry.observe(LATENCY_MS, elapsed_ms, labels=labels)

    def summary(self, plane: str, operation: str) -> Dict[str, Any]:
        labels = {"plane": plane, "op": operation}
        return {
            "plane": plane,
            "op": operation,
            "calls": self.registry.get_counter(CALLS, labels),
            "errors": self.registry.get_counter(ERRORS, labels),
            "latency_ms": self.registry.histogram_stats(LATENCY_MS, labels=labels),
        }

    def traces(self, correlation_id: str) -> list[Dict[str, Any]]:
        """Return finished spans carrying ``correlation_id`` (oldest first)."""

        return [
            span.to_dict()
            for span in self.exporter._spans  # bounded ring owned by the exporter
            if span.attributes.get("correlation_id") == correlation_id
        ]


_default: Optional[PlaneTelemetry] = None


def default_plane_telemetry() -> PlaneTelemetry:
    global _default
    if _default is None:
        _default = PlaneTelemetry()
    return _default


def reset_default_plane_telemetry() -> None:
    """Drop the process-wide instance (tests only)."""

    global _default
    _default = None


def plane_span(plane: str, operation: str, **attributes: Any):
    return default_plane_telemetry().span(plane, operation, **attributes)


def kernel_span(operation: str, **attributes: Any):
    return plane_span("kernel", operation, **attributes)


def agent_span(operation: str, **attributes: Any):
    return plane_span("agents", operation, **attributes)


def api_span(operation: str, **attributes: Any):
    return plane_span("api", operation, **attributes)


__all__ = [
    "CALLS",
    "ERRORS",
    "LATENCY_MS",
    "PLANES",
    "PlaneTelemetry",
    "agent_span",
    "api_span",
    "default_plane_telemetry",
    "kernel_span",
    "plane_span",
    "reset_default_plane_telemetry",
]
