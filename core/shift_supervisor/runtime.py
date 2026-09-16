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
    """Construct the paired manager/secretary runtime around shared state/API.

    The scheduler and research broker share the same captured project snapshot
    for a planning cycle. This avoids re-fetching a large repository/workforce
    context just to collect research for the Manager.
    """
    shared_store = store or InMemoryPlanStore()
    shared_model = model or ModelGateway()
    broker = ResearchBroker(research_sources or {})
    secretary = SecretaryBot(store=shared_store, model=shared_model)
    manager = SMBShiftManager(store=shared_store, model=shared_model)
    latest_context: dict[str, dict[str, Any]] = {}

    def capture_context() -> dict[str, Any]:
        context = project_context_supplier()
        latest_context["value"] = context
        return context

    def collect_research() -> list[dict[str, Any]]:
        context = latest_context.get("value")
        if context is None:
            context = capture_context()
        return broker.collect(context)

    return SupervisorScheduler(
        manager=manager,
        secretary=secretary,
        project_context_supplier=capture_context,
        research_supplier=collect_research,
        cadence=cadence,
    )
