"""Pack F backpressure adapter: Backend Pack H pressure with AdaptiveGate fallback.

Reads Backend's ``skeleton.api.pack_h.admit_pressure.snapshot(tenant_id)``
in-process once the API layer registers it (schema_version 1 only) and falls back to the gate plane's own
``AdaptiveGate`` signal when Pack H is absent, broken or stale. Read-only
against Backend/Pack A modules; no ``api/server.py`` lifespan change.
"""

from __future__ import annotations

from skeleton.gate_plane.backpressure.gate import (
    Action,
    BackpressureDecision,
    BackpressureGate,
    BackpressureStage,
    CONTROL_PRIORITY,
    backpressure_stage_factory,
    default_backpressure_gate,
)
from skeleton.gate_plane.backpressure.registry import (
    register_adaptive_gate,
    register_pressure_provider,
    reset_registry_for_tests,
)
from skeleton.gate_plane.backpressure.snapshot import (
    SCHEMA_VERSION,
    SHED_AT,
    THROTTLE_AT,
    PressureState,
    PressureUnavailable,
    PressureView,
    SchemaMismatch,
    coerce_view,
    derive_state,
    retry_after_header,
)
from skeleton.gate_plane.backpressure.sources import (
    PACK_H_MODULE,
    AdaptiveGateSource,
    CompositeSource,
    FallbackChain,
    PackAPoolSource,
    PackHSource,
    PressureSource,
    StaticSource,
    default_pressure_source,
)

__all__ = [
    "Action",
    "AdaptiveGateSource",
    "BackpressureDecision",
    "BackpressureGate",
    "BackpressureStage",
    "CONTROL_PRIORITY",
    "CompositeSource",
    "FallbackChain",
    "PACK_H_MODULE",
    "PackAPoolSource",
    "PackHSource",
    "PressureSource",
    "PressureState",
    "PressureUnavailable",
    "PressureView",
    "SCHEMA_VERSION",
    "SHED_AT",
    "SchemaMismatch",
    "StaticSource",
    "THROTTLE_AT",
    "backpressure_stage_factory",
    "coerce_view",
    "default_backpressure_gate",
    "default_pressure_source",
    "derive_state",
    "register_adaptive_gate",
    "register_pressure_provider",
    "reset_registry_for_tests",
    "retry_after_header",
]
