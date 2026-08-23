"""Skeleton kernel — public package surface.

The kernel owns the primitives every other subsystem builds on: identity,
the event fabric, causality, liveness, admission, and configuration.
This init re-exports the stable surface so consumers import from
``skeleton.kernel`` and never reach into module files directly.
"""

from .backpressure import (
    BackpressureGovernor,
    LoadShedder,
    Priority,
    ShedDecision,
    TokenBucket,
)
from .breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RetriesExhausted,
    RetryPolicy,
    call_with_protection,
)
from .budget import Budget, BudgetExceeded, BudgetLedger
from .clocks import ClockRegistry, VectorClock, order_events
from .config_snapshots import AuditEntry, ConfigSnapshot, ConfigStore
from .election import Election, Role, StaleTermError, VoteRequest
from .errors import (
    ConfigurationError,
    EventBusError,
    KernelError,
    Severity,
    SkeletonError,
    http_status_for,
)
from .health import HealthRegistry, ProbeResult, ProbeStatus, Rollup
from .leases import Lease, LeaseRegistry
from .shutdown import ShutdownCoordinator, ShutdownPhase
from .supervisor import Health, HeartbeatMonitor, Lifecycle, RestartPolicy, Supervisor
from .trace import Span, SpanRecorder, SpanStatus, TraceContext
from .workqueue import FairWorkQueue, QueueFullError, WorkItem

__all__ = [
    # errors
    "SkeletonError", "Severity", "KernelError", "EventBusError",
    "ConfigurationError", "http_status_for",
    # causality
    "VectorClock", "ClockRegistry", "order_events",
    # admission / flow control
    "BackpressureGovernor", "TokenBucket", "LoadShedder", "Priority",
    "ShedDecision", "FairWorkQueue", "WorkItem", "QueueFullError",
    # failure handling
    "CircuitBreaker", "CircuitState", "CircuitOpenError", "RetryPolicy",
    "RetriesExhausted", "call_with_protection",
    # lifecycle
    "Supervisor", "HeartbeatMonitor", "RestartPolicy", "Health", "Lifecycle",
    "ShutdownCoordinator", "ShutdownPhase",
    # coordination
    "Lease", "LeaseRegistry", "Election", "Role", "VoteRequest",
    "StaleTermError",
    # resources / config
    "Budget", "BudgetLedger", "BudgetExceeded",
    "ConfigStore", "ConfigSnapshot", "AuditEntry",
    # observability
    "TraceContext", "Span", "SpanRecorder", "SpanStatus",
    "HealthRegistry", "ProbeResult", "ProbeStatus", "Rollup",
]
