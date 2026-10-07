"""A handler that has never run is not quality 0.5, and true is not confidence 1."""

import pytest

from skeleton.intelligence.orchestrator import (
    HandlerPolicy,
    HandlerTelemetry,
    IntelligenceOrchestrator,
    ReasoningResult,
)


def test_untried_quality_is_not_half() -> None:
    orchestrator = IntelligenceOrchestrator.__new__(IntelligenceOrchestrator)
    orchestrator._policies = {"fresh": HandlerPolicy(priority=1)}
    orchestrator._telemetry = {"fresh": HandlerTelemetry()}
    assert orchestrator._telemetry["fresh"].success_rate is None
    assert orchestrator._route_score("fresh") == 1.0
    with pytest.raises(ValueError):
        HandlerPolicy(min_confidence=True)
    with pytest.raises(TypeError):
        IntelligenceOrchestrator._validate_result(
            ReasoningResult("t", "answer", True)
        )
    with pytest.raises(ValueError):
        IntelligenceOrchestrator._validate_result(
            ReasoningResult("t", "answer", 0.4, sources=None)
        )
