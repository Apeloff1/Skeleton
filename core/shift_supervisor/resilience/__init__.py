"""Shift Supervisor provider-resilience control plane.

This package is deliberately transport-neutral.  It owns deterministic policy
for classifying provider failures, planning bounded retries, selecting capable
fallback models, maintaining circuit-breaker health, applying backpressure, and
recording safe operational evidence.  Network I/O remains in the caller.

The design goals are:

* bounded work: every request has attempt, delay, and deadline ceilings;
* fail closed: quota, authentication, authorization, and contract failures do
  not silently downgrade into retries;
* capability preservation: fallbacks must satisfy the request's declared tool
  and response capabilities;
* anti-swarm operation: a model or endpoint under pressure is cooled down
  centrally instead of being hammered by many independent workers;
* safe diagnostics: raw provider messages, credentials, prompts, and response
  bodies are not stored in the ledger or telemetry stream;
* deterministic tests: routing and retry plans are reproducible from explicit
  state, without random sleeps or wall-clock races.
"""

from .backpressure import BackpressurePolicy, PressureSignal
from .circuit import CircuitBreakerConfig, CircuitBreakerRegistry
from .engine import ProviderResilienceEngine, ResilienceExecutionError
from .ledger import BoundedRequestLedger
from .models import (
    AttemptBudget,
    AttemptPlan,
    AttemptRecord,
    BackpressureAction,
    BackpressureDecision,
    BackpressureInput,
    Capability,
    CircuitPhase,
    CircuitSnapshot,
    FailureClass,
    FailureDomain,
    HealthGrade,
    LedgerSnapshot,
    ModelCandidate,
    ModelHealth,
    PoolSnapshot,
    ProviderEndpoint,
    RateLimitHints,
    RequestContext,
    RequestOutcome,
    RequestRequirements,
    ResilienceConfig,
    RetryAction,
    SafeProviderError,
    TelemetryEvent,
)
from .pool import ProviderModelPool
from .retry import RetryPolicy, RetryPolicyConfig
from .taxonomy import ProviderErrorClassifier
from .telemetry import InMemoryTelemetry, TelemetryBus

__all__ = [
    "AttemptBudget",
    "AttemptPlan",
    "AttemptRecord",
    "BackpressureAction",
    "BackpressureDecision",
    "BackpressureInput",
    "BackpressurePolicy",
    "BoundedRequestLedger",
    "Capability",
    "CircuitBreakerConfig",
    "CircuitBreakerRegistry",
    "CircuitPhase",
    "CircuitSnapshot",
    "FailureClass",
    "FailureDomain",
    "HealthGrade",
    "InMemoryTelemetry",
    "LedgerSnapshot",
    "ModelCandidate",
    "ModelHealth",
    "PoolSnapshot",
    "PressureSignal",
    "ProviderEndpoint",
    "ProviderErrorClassifier",
    "ProviderModelPool",
    "ProviderResilienceEngine",
    "RateLimitHints",
    "RequestContext",
    "RequestOutcome",
    "RequestRequirements",
    "ResilienceConfig",
    "ResilienceExecutionError",
    "RetryAction",
    "RetryPolicy",
    "RetryPolicyConfig",
    "SafeProviderError",
    "TelemetryBus",
    "TelemetryEvent",
]
