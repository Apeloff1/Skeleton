"""Simulated planning findings never constitute production verification."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from skeleton.ai.runtime.deferred.cognitive_tools import (
    PlanSimulation,
    SimulatedStep,
    SimulationFinding,
    simulate_plan,
)


def test_production_evidence_descriptor_is_callable_and_always_false() -> None:
    descriptor = PlanSimulation.production_evidence
    assert isinstance(descriptor, property)
    assert callable(descriptor.fget)
    plan = simulate_plan(("design", "verify"))
    assert plan.production_evidence is False
    assert descriptor.fget(plan) is False


def test_all_simulation_outcomes_remain_nonproduction() -> None:
    plan = simulate_plan(("build", "review", "release"))
    assert len(plan.steps) == 12
    assert all(step.outcome == "simulated" for step in plan.steps)
    assert len(plan.findings) == 3
    assert plan.production_evidence is False


def test_custom_findings_cannot_promote_plan_to_production() -> None:
    plan = PlanSimulation(
        steps=(SimulatedStep("step-1", "success", "simulated"),),
        findings=(SimulationFinding("failure", "simulated adverse outcome"),),
    )
    assert plan.production_evidence is False
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        plan.production_evidence = True
