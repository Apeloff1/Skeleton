from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    DenseTensor,
    MathInvariantError,
    adaptive_simpson,
    correlation,
    covariance_matrix,
    dominant_eigenpair_symmetric,
    dominant_frequency,
    dual_exp,
    dual_sin,
    gradient,
    jacobian,
    median_absolute_deviation,
    moments,
    quantile,
    rk4_integrate,
    spectral_power_fraction,
    standardize,
    tensor_add,
    tensor_multiply,
    tensor_reduce_mean,
    tensor_reduce_sum,
)


def test_dual_gradient_matches_closed_form() -> None:
    def function(values):
        x, y = values
        return x * y + dual_sin(x) + dual_exp(y)

    point = (0.7, -0.2)
    result = gradient(function, point)
    expected = (
        point[1] + math.cos(point[0]),
        point[0] + math.exp(point[1]),
    )
    assert result == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_dual_jacobian_preserves_output_and_input_dimensions() -> None:
    def function(values):
        x, y = values
        return (x * y, x * x + y)

    result = jacobian(function, (2.0, 3.0))
    assert result[0] == pytest.approx((3.0, 2.0), abs=1e-12)
    assert result[1] == pytest.approx((4.0, 1.0), abs=1e-12)


def test_tensor_broadcast_transpose_and_reduction_contracts() -> None:
    matrix = DenseTensor.matrix(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
    bias = DenseTensor.vector((10.0, 20.0, 30.0))
    shifted = tensor_add(matrix, bias)
    assert shifted.shape == (2, 3)
    assert shifted.data == pytest.approx((11.0, 22.0, 33.0, 14.0, 25.0, 36.0))

    scaled = tensor_multiply(shifted, DenseTensor.vector((1.0, 0.5, 2.0)))
    assert scaled.data == pytest.approx((11.0, 11.0, 66.0, 14.0, 12.5, 72.0))
    assert scaled.transpose().shape == (3, 2)
    assert scaled.transpose().data == pytest.approx((11.0, 14.0, 11.0, 12.5, 66.0, 72.0))

    row_sum = tensor_reduce_sum(matrix, axis=1)
    assert row_sum.shape == (2,)
    assert row_sum.data == pytest.approx((6.0, 15.0))
    column_mean = tensor_reduce_mean(matrix, axis=0)
    assert column_mean.shape == (3,)
    assert column_mean.data == pytest.approx((2.5, 3.5, 4.5))


def test_tensor_invalid_broadcast_fails_closed() -> None:
    left = DenseTensor.zeros((2, 3))
    right = DenseTensor.zeros((4,))
    with pytest.raises(MathInvariantError, match="broadcast"):
        tensor_add(left, right)


def test_symmetric_power_iteration_reports_residual() -> None:
    report = dominant_eigenpair_symmetric(((2.0, 1.0), (1.0, 2.0)))
    assert report.converged
    assert report.eigenvalue == pytest.approx(3.0, abs=1e-10)
    assert report.residual_l2 <= 1e-10
    expected = 1.0 / math.sqrt(2.0)
    assert report.eigenvector == pytest.approx((expected, expected), abs=1e-8)


def test_periodogram_recovers_known_harmonic() -> None:
    observations = tuple(math.sin(2.0 * math.pi * index / 8.0) for index in range(32))
    peak = dominant_frequency(observations)
    assert peak.bin_index == 4
    assert peak.frequency == pytest.approx(1.0 / 8.0)
    assert spectral_power_fraction(observations, (4,)) > 0.999999


def test_adaptive_simpson_integrates_sine_and_tracks_orientation() -> None:
    forward = adaptive_simpson(math.sin, 0.0, math.pi)
    reverse = adaptive_simpson(math.sin, math.pi, 0.0)
    assert forward.converged
    assert forward.integral == pytest.approx(2.0, abs=1e-10)
    assert reverse.integral == pytest.approx(-2.0, abs=1e-10)
    assert forward.evaluations >= 5
    assert forward.absolute_error_estimate >= 0.0


def test_rk4_tracks_exponential_growth() -> None:
    def derivative(_time, state):
        return state

    report = rk4_integrate(derivative, 0.0, 1.0, (1.0,), steps=100)
    assert len(report.points) == 101
    assert report.points[-1].time == pytest.approx(1.0)
    assert report.points[-1].state[0] == pytest.approx(math.e, rel=2e-9)


def test_stable_statistics_and_robust_location_contracts() -> None:
    values = (1.0, 2.0, 3.0, 4.0, 100.0)
    report = moments(values)
    assert report.count == 5
    assert report.mean == pytest.approx(22.0)
    assert quantile(values, 0.5) == pytest.approx(3.0)
    assert median_absolute_deviation(values) == pytest.approx(1.0)

    standardized = standardize((1.0, 2.0, 3.0))
    assert moments(standardized).mean == pytest.approx(0.0, abs=1e-15)
    assert moments(standardized).population_variance == pytest.approx(1.0, abs=1e-12)


def test_covariance_matrix_is_symmetric_and_correlation_is_bounded() -> None:
    rows = (
        (1.0, 2.0, -1.0),
        (2.0, 4.0, -2.0),
        (3.0, 6.0, -3.0),
        (4.0, 8.0, -4.0),
    )
    matrix = covariance_matrix(rows)
    assert matrix[0][1] == pytest.approx(matrix[1][0])
    assert matrix[0][2] == pytest.approx(matrix[2][0])
    assert correlation((1.0, 2.0, 3.0), (2.0, 4.0, 6.0)) == pytest.approx(1.0)
    assert correlation((1.0, 2.0, 3.0), (3.0, 2.0, 1.0)) == pytest.approx(-1.0)
