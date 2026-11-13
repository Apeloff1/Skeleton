import pytest

from skeleton.gameforge.batch_b074 import Budget, BudgetError, BudgetGate, Metric, TargetBudgets
from skeleton.gameforge.batch_b074.budgets import percentile


def _gate():
    mobile = TargetBudgets("mobile").add(Budget(Metric.FRAME_MS, 33.3)).add(Budget(Metric.MEMORY_MB, 512))
    desktop = TargetBudgets("desktop").add(Budget(Metric.FRAME_MS, 16.7))
    return BudgetGate([mobile, desktop])


def test_target_specific_ceilings():
    frames = [20.0] * 100
    g = _gate()
    assert g.check("mobile", {Metric.FRAME_MS: frames, Metric.MEMORY_MB: [300]}).passed
    assert not g.check("desktop", {Metric.FRAME_MS: frames}).passed


def test_percentile_catches_spikes():
    frames = [10.0] * 90 + [50.0] * 10
    r = _gate().check("desktop", {Metric.FRAME_MS: frames})
    assert not r.passed and "p95" in r.violations[0]
    assert percentile([1, 2, 3, 4], 50) == 2


def test_missing_metric_fails_closed():
    r = _gate().check("mobile", {Metric.FRAME_MS: [10.0]})
    assert not r.passed and "memory_mb: missing samples" in r.violations


def test_regression_against_baseline():
    r = _gate().check("desktop", {Metric.FRAME_MS: [12.0]}, baseline={Metric.FRAME_MS: 10.0})
    assert not r.passed and "regression" in r.violations[0]
    assert _gate().check("desktop", {Metric.FRAME_MS: [10.4]}, baseline={Metric.FRAME_MS: 10.0}).passed


def test_validation():
    with pytest.raises(BudgetError):
        Budget(Metric.CPU_MS, 0)
    with pytest.raises(BudgetError):
        TargetBudgets("x").add(Budget(Metric.CPU_MS, 1)).add(Budget(Metric.CPU_MS, 2))
    with pytest.raises(BudgetError):
        _gate().check("console", {})
