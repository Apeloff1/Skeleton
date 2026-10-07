"""A router does not return an answer the model did not give."""

import pytest

from skeleton.intelligence.cascade import CascadeRouter, ModelResponse
from skeleton.intelligence.economic import BudgetConstraint, EconomicOptimiser, ModelOption


def test_an_impossible_confidence_is_not_a_cheap_answer() -> None:
    def cheap(query: str) -> ModelResponse:
        return ModelResponse("guess", 5)

    def strong(query: str) -> ModelResponse:
        return ModelResponse("checked", 0.8)

    router = CascadeRouter(cheap, strong, cheap_cost=1, strong_cost=10)
    decision = router.route("hello")
    assert decision.model == "strong"
    assert decision.text == "checked"
    assert decision.escalated is True
    assert router.total_cost == 11
    with pytest.raises(ValueError):
        router.route("   ")
    assert router.total_cost == 11

    def boom(query: str) -> ModelResponse:
        raise RuntimeError("secret")

    failed = CascadeRouter(boom, strong)
    with pytest.raises(RuntimeError):
        failed.route("hello")
    assert failed.total_cost == 0


def test_complexity_and_model_cost_are_not_clamped_into_range() -> None:
    optimiser = EconomicOptimiser()
    with pytest.raises(ValueError):
        optimiser.register_model(ModelOption("pay-me", -1, 0.9, 10, {"search"}))
    optimiser.register_model(ModelOption("small", 0.01, 0.4, 20, {"search"}))
    constraint = BudgetConstraint(1, 1, 0.1, 100)
    with pytest.raises(ValueError):
        optimiser.route_query(5, {"search"}, constraint)
    chosen = optimiser.route_query(0.2, {"search"}, constraint, token_estimate=10)
    assert chosen.model_id == "small"
