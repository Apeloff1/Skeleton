from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    compensated_sum,
    effective_sample_size,
    entropy,
    jensen_shannon_divergence,
    kl_divergence,
    logsumexp,
    projected_gradient_descent,
    solve_linear_system,
    stable_softmax,
    weighted_moments,
)
from skeleton.ai.mathematics.validation import audit_runtime_kernels


def test_compensated_sum_recovers_cancellation_signal() -> None:
    assert sum([1e16, 1.0, -1e16]) == 0.0
    assert compensated_sum([1e16, 1.0, -1e16]) == 1.0


def test_logsumexp_and_softmax_are_shift_stable() -> None:
    logits = (1000.0, 999.0, 997.0)
    shifted = tuple(value - 5000.0 for value in logits)
    left = stable_softmax(logits)
    right = stable_softmax(shifted)
    assert left == pytest.approx(right, abs=1e-15, rel=1e-12)
    assert sum(left) == pytest.approx(1.0, abs=1e-15)
    assert logsumexp(logits) - logsumexp(shifted) == pytest.approx(5000.0)


def test_linear_solve_reports_small_residual() -> None:
    report = solve_linear_system(
        ((4.0, 1.0, -1.0), (2.0, 7.0, 1.0), (1.0, -3.0, 12.0)),
        (3.0, 19.0, 31.0),
    )
    assert report.solution == pytest.approx((1.0, 2.0, 3.0), abs=1e-12)
    assert report.residual_linf <= 1e-12
    assert report.pivot_condition_proxy >= 1.0


def test_probability_information_invariants() -> None:
    p = (0.2, 0.3, 0.5)
    q = (0.25, 0.25, 0.5)
    assert entropy(p) > 0.0
    assert kl_divergence(p, p) == pytest.approx(0.0, abs=1e-15)
    assert kl_divergence(p, q) >= 0.0
    js = jensen_shannon_divergence(p, q)
    assert 0.0 <= js <= math.log(2.0)
    assert effective_sample_size((1.0, 1.0, 1.0, 1.0)) == pytest.approx(4.0)
    mean, variance = weighted_moments((1.0, 3.0), (1.0, 1.0))
    assert mean == pytest.approx(2.0)
    assert variance == pytest.approx(1.0)


def test_projected_gradient_descent_converges_without_crossing_bounds() -> None:
    def objective(point: tuple[float, ...]) -> float:
        x, y = point
        return (x - 3.0) ** 2 + 4.0 * (y + 2.0) ** 2

    result = projected_gradient_descent(
        objective,
        (20.0, 20.0),
        bounds=((-10.0, 4.0), (-3.0, 10.0)),
    )
    assert result.converged
    assert result.point == pytest.approx((3.0, -2.0), abs=2e-5)
    assert result.objective <= 1e-8
    assert all(step.step_size >= 0.0 for step in result.trace)


def test_non_finite_inputs_fail_closed() -> None:
    with pytest.raises(MathInvariantError, match="finite"):
        stable_softmax((1.0, float("nan")))
    with pytest.raises(MathInvariantError, match="finite"):
        solve_linear_system(((1.0, 0.0), (0.0, float("inf"))), (1.0, 1.0))
    with pytest.raises(MathInvariantError, match="support"):
        kl_divergence((1.0, 0.0), (0.0, 1.0))


def test_runtime_kernel_reference_oracle_matches_current_implementations() -> None:
    report = audit_runtime_kernels()
    assert report.passed, report.cases
    assert len(report.fingerprint) == 64
    assert {case.name for case in report.cases} == {
        "softmax.extreme_shift",
        "matmul.reference_parity",
        "attention.row_reference_parity",
    }
