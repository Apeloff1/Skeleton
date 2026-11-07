"""Unit tests for the B031 compat ModelRouter adapter."""

from __future__ import annotations

from skeleton.ai.compat.backend_core.model_router import ModelEndpoint, ModelRouter
from skeleton.ai.compat.backend_core.model_router_adapter import (
    CompatModelRouterAdapter,
    parse_no_route_detail,
)
from skeleton.frontier.runtime.model_router_contract import CallBudget, RouteStatus, RouteTask


def _router() -> ModelRouter:
    router = ModelRouter()
    router.register(ModelEndpoint("cheap", "acme", "m-small", capabilities=frozenset({"chat"}),
                                  max_context_tokens=8000, input_cost_per_million=1.0,
                                  output_cost_per_million=1.0, nominal_latency_ms=100.0))
    router.register(ModelEndpoint("big", "other", "m-large", capabilities=frozenset({"chat"}),
                                  max_context_tokens=8000, input_cost_per_million=50.0,
                                  output_cost_per_million=50.0, nominal_latency_ms=900.0))
    return router


def _task(**kw) -> RouteTask:
    base = dict(task_type="chat", required_capabilities=frozenset({"chat"}),
                estimated_input_tokens=100, expected_output_tokens=100, request_id="r1")
    base.update(kw)
    return RouteTask(**base)


def test_select_plans_chain_with_fallback():
    receipt = CompatModelRouterAdapter(_router(), clock=lambda: 1.0).select(_task())
    assert receipt.status == RouteStatus.PLANNED
    assert receipt.backend == "compat"
    assert {receipt.selected_provider_id, *receipt.fallback_chain} == {"cheap", "big"}
    assert receipt.decided_at == 1.0


def test_preferred_ids_lead_and_max_attempts_trims():
    receipt = CompatModelRouterAdapter(_router()).select(
        _task(preferred_providers=("big",)), CallBudget(max_attempts=1))
    assert receipt.selected_provider_id == "big"
    assert receipt.fallback_chain == ()
    assert receipt.rejected["cheap"] == ("beyond budget.max_attempts",)


def test_excluded_provider_name_filters_endpoint():
    receipt = CompatModelRouterAdapter(_router()).select(_task(excluded_providers=frozenset({"other"})))
    assert receipt.selected_provider_id == "cheap"
    assert "big" not in receipt.fallback_chain


def test_no_route_reports_status():
    receipt = CompatModelRouterAdapter(_router()).select(
        _task(required_capabilities=frozenset({"vision-only"})))
    assert receipt.status in (RouteStatus.NO_ROUTE, RouteStatus.BUDGET_EXHAUSTED)
    assert receipt.selected_provider_id is None


def test_parse_no_route_detail():
    msg = "no endpoint satisfies route request (a: cost exceeds budget, slow; b: disabled)"
    assert parse_no_route_detail(msg) == {"a": ("cost exceeds budget", "slow"), "b": ("disabled",)}
    assert parse_no_route_detail("weird") == {"*": ("weird",)}
    assert parse_no_route_detail("") == {}
