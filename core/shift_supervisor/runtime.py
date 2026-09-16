from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .model_gateway import ModelGateway
from .plan_store import InMemoryPlanStore
from .research import ResearchBroker
from .scheduler import SupervisorCadence, SupervisorScheduler
from .secretary import SecretaryBot
from .shift_manager import SMBShiftManager


def build_supervisor(
    *,
    project_context_supplier: Callable[[], dict[str, Any]],
    research_sources: dict[str, Callable[[dict[str, Any]], Any]] | None = None,
    store: InMemoryPlanStore | None = None,
    model: ModelGateway | None = None,
    cadence: SupervisorCadence | None = None,
) -> SupervisorScheduler:
    """Construct the paired manager/secretary runtime around shared state/API."""
    shared_store = store or InMemoryPlanStore()
    shared_model = model or ModelGateway()
    broker = ResearchBroker(research_sources or {})
    secretary = SecretaryBot(store=shared_store, model=shared_model)
    manager = SMBShiftManager(store=shared_store, model=shared_model)
    return SupervisorScheduler(
        manager=manager,
        secretary=secretary,
        project_context_supplier=project_context_supplier,
        research_supplier=lambda: broker.collect(project_context_supplier()),
        cadence=cadence,
    )
