"""
gameforge.prood — PROOD architecture patterns (real implementations).

The uploaded PROOD_CODE zip shipped skeletal stubs (a trivial pub/sub EventBus
and a Saga with NO compensation/recovery). This package implements those
patterns properly — the EventBus is async + error-isolated with history, the
SagaOrchestrator does forward execution with automatic compensation (rollback
in reverse) on failure, and (Stage B) a REAL N-replica Byzantine quorum plus a
durable EventBus→Mongo sink.
"""
from gameforge.prood.event_bus import EventBus, event_bus
from gameforge.prood.saga_orchestrator import (
    SagaOrchestrator, SagaStep, SagaResult, saga_orchestrator,
)
from gameforge.prood.quorum import (
    QuorumConsensus, QuorumResult, Replica, quorum_consensus,
)
from gameforge.prood.event_sink import install_event_sink, recent_events

# Attach the durable event sink at import time so every publish is mirrored to
# Mongo (idempotent — installs exactly once).
try:
    install_event_sink()
except Exception:  # noqa: BLE001
    pass

__all__ = [
    "EventBus", "event_bus",
    "SagaOrchestrator", "SagaStep", "SagaResult", "saga_orchestrator",
    "QuorumConsensus", "QuorumResult", "Replica", "quorum_consensus",
    "install_event_sink", "recent_events",
]
