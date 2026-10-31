"""Pressure-aware deterministic prefill/decode scheduling."""
from __future__ import annotations
import pytest
from skeleton.ai.model_runtime.iteration_scheduler import (
    InferencePhase, IterationScheduler, IterationWork,
)

def _work() -> tuple[IterationWork, ...]:
    return (
        IterationWork("prefill", InferencePhase.PREFILL, 1000),
        IterationWork("decode", InferencePhase.DECODE, 1000),
    )

def test_pressure_reduces_iteration_budget_without_mutating_operator_limit() -> None:
    scheduler = IterationScheduler(token_budget=100, prefill_quantum=100)
    normal = scheduler.plan_pressure_aware(_work(), measured_pressure_fraction=0.0, source="linux_psi")
    high = scheduler.plan_pressure_aware(_work(), measured_pressure_fraction=0.9, source="linux_psi")
    assert normal.effective_token_budget == 100
    assert high.effective_token_budget == 10
    assert high.plan.used_tokens <= 10
    assert scheduler.token_budget == 100
    assert high.digest != normal.digest

def test_decode_gets_priority_under_pressure() -> None:
    scheduler = IterationScheduler(token_budget=10, prefill_quantum=10)
    receipt = scheduler.plan_pressure_aware(_work(), measured_pressure_fraction=0.9, source="linux_psi")
    assert receipt.plan.slices[0].request_id == "decode"

def test_minimum_budget_prevents_zero_progress() -> None:
    scheduler = IterationScheduler(token_budget=100)
    receipt = scheduler.plan_pressure_aware(_work(), measured_pressure_fraction=1.0, source="linux_psi", minimum_tokens=2)
    assert receipt.effective_token_budget == 2
    assert receipt.plan.used_tokens == 2

def test_identical_measurements_are_deterministic() -> None:
    scheduler = IterationScheduler(token_budget=100)
    first = scheduler.plan_pressure_aware(_work(), measured_pressure_fraction=0.5, source="cgroup")
    second = scheduler.plan_pressure_aware(_work(), measured_pressure_fraction=0.5, source="cgroup")
    assert first == second

@pytest.mark.parametrize("pressure", [None, True, -0.1, 1.1, float("nan"), float("inf")])
def test_untrusted_pressure_rejected(pressure: object) -> None:
    with pytest.raises(ValueError):
        IterationScheduler().plan_pressure_aware(_work(), measured_pressure_fraction=pressure, source="linux_psi")

@pytest.mark.parametrize("source", ["", "unavailable", "bad\nsource", 42])
def test_untrusted_provenance_rejected(source: object) -> None:
    with pytest.raises(ValueError):
        IterationScheduler().plan_pressure_aware(_work(), measured_pressure_fraction=0.1, source=source)

def test_work_item_bound_prevents_unbounded_sort() -> None:
    scheduler = IterationScheduler()
    with pytest.raises(ValueError, match="bounded tuple"):
        scheduler.plan(tuple(IterationWork(str(i), InferencePhase.PREFILL, 1) for i in range(65_537)))

def test_bad_request_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        IterationWork("bad\nidentity", InferencePhase.DECODE, 1)
