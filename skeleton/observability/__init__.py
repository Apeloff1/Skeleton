"""Observability subsystem — metrics, tracing, health, alerts, logging, emergent-coupling."""

from .entanglement import Entanglement, EntanglementDetector
from .health import HealthRegistry, ProbeResult, probe
from .metrics import Counter, Gauge, Histogram, MetricsRegistry
from .tracing import InMemoryExporter, Span, SpanContext, Tracer
from .alerting import AlertRule, AlertingEngine, NotificationRouter, Severity, Operator
from .profiling import Profiler, SpanStats
from .logging import LogEvent, LogError, StructuredLogger

__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "ProbeResult",
    "HealthRegistry",
    "probe",
    "Span",
    "Tracer",
    "InMemoryExporter",
    "SpanContext",
    "Entanglement",
    "EntanglementDetector",
    "AlertRule",
    "AlertingEngine",
    "NotificationRouter",
    "Severity",
    "Operator",
    "Profiler",
    "SpanStats",
    "LogEvent",
    "LogError",
    "StructuredLogger",
]
