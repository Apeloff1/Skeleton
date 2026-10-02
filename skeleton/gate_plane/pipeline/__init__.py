"""Pack F composable request pipeline for the gate plane.

Timeouts (total deadline + per-attempt), retries bounded by a shared
budget, and a per-upstream circuit breaker, composed in an order that is
validated at build time. Pure library code with injectable clocks — no
host side effects and no changes to ``skeleton/api/server.py``.
"""

from __future__ import annotations

from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry, BreakerState, CircuitBreaker
from skeleton.gate_plane.pipeline.budget import Deadline, RetryBudget, RetryBudgetRegistry
from skeleton.gate_plane.pipeline.core import (
    CANONICAL_ORDER,
    CallContext,
    FunctionStage,
    Pipeline,
    PipelineRequest,
    PipelineResponse,
    Stage,
    validate_order,
)
from skeleton.gate_plane.pipeline.errors import (
    AttemptTimeout,
    BreakerOpenError,
    DeadlineExceeded,
    PipelineConfigError,
    PipelineError,
    RetryBudgetExhausted,
)
from skeleton.gate_plane.pipeline.retry import RetrySpec, Verdict
from skeleton.gate_plane.pipeline.routes import PipelineRouter, RouteConfig, RouteTable, default_s2s_routes
from skeleton.gate_plane.pipeline.stages import AttemptTimeoutStage, BreakerStage, DeadlineStage, RetryStage

__all__ = [
    "AttemptTimeout",
    "AttemptTimeoutStage",
    "BreakerConfig",
    "BreakerOpenError",
    "BreakerRegistry",
    "BreakerStage",
    "BreakerState",
    "CANONICAL_ORDER",
    "CallContext",
    "CircuitBreaker",
    "Deadline",
    "DeadlineExceeded",
    "DeadlineStage",
    "FunctionStage",
    "Pipeline",
    "PipelineConfigError",
    "PipelineError",
    "PipelineRequest",
    "PipelineResponse",
    "PipelineRouter",
    "RetryBudget",
    "RetryBudgetExhausted",
    "RetryBudgetRegistry",
    "RetrySpec",
    "RetryStage",
    "RouteConfig",
    "RouteTable",
    "Stage",
    "Verdict",
    "default_s2s_routes",
    "validate_order",
]
