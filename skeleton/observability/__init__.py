"""Observability subsystem — full surface with uptime tracking."""

from .alerting import AlertRule, AlertingEngine, NotificationRouter, Operator, Severity
from .coverage import CoverageRegistry, CoverageAudit
from .dashboards import Dashboard, DashboardError, Widget, aggregate
from .entanglement import Entanglement, EntanglementDetector
from .exporters import MetricsExporter, TraceExporter
from .health import HealthRegistry, ProbeResult, probe
from .incidents import Incident, IncidentError, IncidentStatus, IncidentTracker
from .logging import LogEvent, LogError, StructuredLogger
from .metrics import Counter, Gauge, Histogram, MetricsRegistry
from .profiling import Profiler, SpanStats
from .sampling import Sampler, SamplerStats, SamplingError, default_sampler
from .slo import ErrorBudget, SLOError, SLOTracker, ServiceLevelObjective
from .ticks import TickAggregator, TickStats
from .tracing import InMemoryExporter, Span, SpanContext, Tracer
from .uptime import AvailabilityWindow, UptimeTracker

__all__ = [
    "AlertRule",
    "AlertingEngine",
    "NotificationRouter",
    "Operator",
    "Severity",
    "CoverageRegistry",
    "CoverageAudit",
    "Dashboard",
    "DashboardError",
    "Widget",
    "aggregate",
    "Entanglement",
    "EntanglementDetector",
    "MetricsExporter",
    "TraceExporter",
    "HealthRegistry",
    "ProbeResult",
    "probe",
    "Incident",
    "IncidentError",
    "IncidentStatus",
    "IncidentTracker",
    "LogEvent",
    "LogError",
    "StructuredLogger",
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "Profiler",
    "SpanStats",
    "Sampler",
    "SamplerStats",
    "SamplingError",
    "default_sampler",
    "ErrorBudget",
    "SLOError",
    "SLOTracker",
    "ServiceLevelObjective",
    "TickAggregator",
    "TickStats",
    "InMemoryExporter",
    "Span",
    "SpanContext",
    "Tracer",
    "AvailabilityWindow",
    "UptimeTracker",
]
