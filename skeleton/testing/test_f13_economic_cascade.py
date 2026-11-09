"""F-13: EconomicOptimiser and CascadeRouter share one routing contract."""

from __future__ import annotations

import pytest

from skeleton.intelligence.cascade import CascadeRouter, ModelResponse
from skeleton.intelligence.economic import BudgetConstraint, EconomicOptimiser, ModelOption


def _option(
    model_id: str,
    *,
    cost: float,
    quality: float,
    latency: float = 100.0,
    capabilities: set[str] | None = None,
) -> ModelOption:
    return ModelOption(
        model_id=model_id,
        cost_per_token=cost,
        quality_score=quality,
        latency_ms=latency,
        capabilities=capabilities or {"chat"},
    )


def _constraint(
    *,
    total: float = 10.0,
    per_query: float = 10.0,
    quality: float = 0.75,
    latency: float = 500.0,
) -> BudgetConstraint:
    return BudgetConstraint(
        total_budget=total,
        max_cost_per_query=per_query,
        min_quality=quality,
        max_latency_ms=latency,
    )


def _optimiser() -> EconomicOptimiser:
    optimiser = EconomicOptimiser()
    optimiser.register_model(_option("economy", cost=0.001, quality=0.80, latency=80))
    optimiser.register_model(_option("middle", cost=0.002, quality=0.87, latency=120))
    optimiser.register_model(_option("frontier", cost=0.004, quality=0.96, latency=220))
    return optimiser


def test_cascade_router_keeps_legacy_role_labels_by_default():
    router = CascadeRouter(
        lambda _q: ModelResponse("cheap", 0.9),
        lambda _q: ModelResponse("strong", 0.99),
    )
    decision = router.route("hello")
    assert decision.model == "cheap"
    assert decision.text == "cheap"


def test_plan_cascade_uses_cheapest_and_highest_quality_eligible_models():
    optimiser = _optimiser()
    plan = optimiser.plan_cascade({"chat"}, _constraint(), token_estimate=1000)
    assert plan is not None
    assert plan.cheap_model_id == "economy"
    assert plan.strong_model_id == "frontier"
    assert plan.cheap_cost == pytest.approx(1.0)
    assert plan.strong_cost == pytest.approx(4.0)
    assert not plan.single_model


def test_plan_cascade_applies_budget_before_assigning_roles():
    optimiser = _optimiser()
    plan = optimiser.plan_cascade(
        {"chat"},
        _constraint(total=2.5, per_query=2.5),
        token_estimate=1000,
    )
    assert plan is not None
    assert plan.cheap_model_id == "economy"
    assert plan.strong_model_id == "middle"
    assert plan.strong_cost == pytest.approx(2.0)


def test_build_cascade_uses_registry_ids_and_economic_costs_on_escalation():
    optimiser = _optimiser()
    router = optimiser.build_cascade_router(
        {
            "economy": lambda _q: ModelResponse("draft", 0.10),
            "middle": lambda _q: ModelResponse("middle", 0.80),
            "frontier": lambda _q: ModelResponse("final", 0.99),
        },
        {"chat"},
        _constraint(),
        token_estimate=1000,
        route_threshold=1.0,
        escalate_below=0.55,
    )
    assert router is not None

    decision = router.route("hello")
    assert decision.model == "frontier"
    assert decision.escalated is True
    assert decision.reason == "confidence_escalation"
    assert router.total_cost == pytest.approx(5.0)


def test_build_cascade_preserves_direct_strong_model_identity():
    optimiser = _optimiser()
    router = optimiser.build_cascade_router(
        {
            "economy": lambda _q: ModelResponse("draft", 0.99),
            "middle": lambda _q: ModelResponse("middle", 0.99),
            "frontier": lambda _q: ModelResponse("final", 0.99),
        },
        {"chat"},
        _constraint(),
        route_threshold=0.0,
    )
    assert router is not None

    decision = router.route("anything")
    assert decision.model == "frontier"
    assert decision.reason == "difficulty_threshold"
    assert router.total_cost == pytest.approx(4.0)


def test_build_cascade_rejects_missing_runtime_callable():
    optimiser = _optimiser()
    with pytest.raises(KeyError, match="frontier"):
        optimiser.build_cascade_router(
            {"economy": lambda _q: ModelResponse("draft", 0.9)},
            {"chat"},
            _constraint(),
        )


def test_route_query_records_real_token_cost_statistics():
    optimiser = _optimiser()
    chosen = optimiser.route_query(
        0.0,
        {"chat"},
        _constraint(),
        token_estimate=1500,
    )
    assert chosen is not None
    assert chosen.model_id == "economy"
    assert optimiser.get_cost_statistics() == {
        "queries": 1,
        "total_cost": pytest.approx(1.5),
        "average_cost": pytest.approx(1.5),
        "models_used": 1,
    }


def test_allocate_budget_uses_each_query_token_estimate_before_routing():
    optimiser = EconomicOptimiser()
    optimiser.register_model(_option("only", cost=0.001, quality=0.9))
    allocation = optimiser.allocate_budget(
        [
            {"id": "too-large", "complexity": 1.0, "token_estimate": 2000, "capabilities": ["chat"]},
            {"id": "fits", "complexity": 0.5, "token_estimate": 1000, "capabilities": ["chat"]},
        ],
        _constraint(total=2.0, per_query=1.5),
    )
    assert allocation == {"only": ["fits"]}
    stats = optimiser.get_cost_statistics()
    assert stats["queries"] == 1
    assert stats["total_cost"] == pytest.approx(1.0)


def test_invalid_token_estimates_and_thresholds_fail_closed():
    optimiser = _optimiser()
    with pytest.raises(ValueError, match="positive integer"):
        optimiser.route_query(0.5, {"chat"}, _constraint(), token_estimate=True)
    with pytest.raises(ValueError, match="positive integer"):
        optimiser.plan_cascade({"chat"}, _constraint(), token_estimate=0)
    with pytest.raises(ValueError, match="route_threshold"):
        optimiser.plan_cascade({"chat"}, _constraint(), route_threshold=1.1)


def test_no_economically_eligible_model_returns_none_for_both_apis():
    optimiser = _optimiser()
    impossible = _constraint(total=0.5, per_query=0.5, quality=0.99)
    assert optimiser.route_query(0.5, {"chat"}, impossible) is None
    assert optimiser.plan_cascade({"chat"}, impossible) is None
    assert (
        optimiser.build_cascade_router({}, {"chat"}, impossible)
        is None
    )
