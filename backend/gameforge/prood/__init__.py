"""
gameforge.prood — PROOD architecture patterns (real implementations).

The uploaded PROOD_CODE zip shipped skeletal stubs (a trivial pub/sub EventBus
and a Saga with NO compensation/recovery). This package implements those
patterns properly — the EventBus is async + error-isolated with history, and
the SagaOrchestrator does forward execution with automatic compensation
(rollback in reverse) on failure, which is what the PROOD doc's
"Saga Pattern with full compensation and recovery" actually requires.
"""
from gameforge.prood.event_bus import EventBus, event_bus
from gameforge.prood.saga_orchestrator import (
    SagaOrchestrator, SagaStep, SagaResult, saga_orchestrator,
)

__all__ = [
    "EventBus", "event_bus",
    "SagaOrchestrator", "SagaStep", "SagaResult", "saga_orchestrator",
]
