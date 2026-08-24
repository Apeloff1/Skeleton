"""Observability subsystem — metrics, tracing, health, emergent-coupling detection."""

from .entanglement import Entanglement, EntanglementDetector
from .health import HealthRegistry, ProbeResult, probe
from .metrics import Counter, Gauge, Histogram, MetricsRegistry
from .tracing import InMemoryExporter, Span, SpanContext, Tracer

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
]
