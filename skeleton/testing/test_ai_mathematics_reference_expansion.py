from __future__ import annotations

import cmath
import math

import pytest

from skeleton.ai.mathematics import (
    CSRMatrix,
    MathInvariantError,
    barycentric_interpolate,
    binary_calibration_report,
    chebyshev_nodes,
    autocorrelation,
    convolution,
    dft,
    fft_radix2,
    gaussian_mixture_log_density,
    horner,
    inverse_fft_radix2,
    newton_divided_differences,
    newton_interpolate,
    normal_cdf,
    normal_log_pdf,
    normal_quantile,
    piecewise_linear_interpolate,
    poisson_log_pmf,
    sparse_dense_matmul,
    student_t_log_pdf,
    top_label_calibration_report,
)


def test_csr_from_coo_merges_duplicates_and_preserves_matvec() -> None:
    matrix = CSRMatrix.from_coo(
        (3, 3),
        (0, 0, 0, 1, 2),
        (0, 0, 2, 1, 0),
        (1.0, 2.0, 4.0, 5.0, -1.0),
    )
    assert matrix.nnz == 4
    assert matrix.to_dense() == (
        (3.0, 0.0, 4.0),
        (0.0, 5.0, 0.0),
        (-1.0, 0.0, 0.0),
    )
    assert matrix.matvec((2.0, 3.0, 4.0)) == pytest.approx((22.0, 15.0, -2.0))
    assert matrix.transpose().to_dense() == (
        (3.0, 0.0, -1.0),
        (0.0, 5.0, 0.0),
        (4.0, 0.0, 0.0),
    )


def test_sparse_dense_matmul_matches_dense_reference() -> None:
    left = CSRMatrix.from_dense(((1.0, 0.0, 2.0), (0.0, 3.0, 0.0)))
    right = ((2.0, 1.0), (4.0, -1.0), (5.0, 2.0))
    result = sparse_dense_matmul(left, right)
    assert result[0] == pytest.approx((12.0, 5.0))
    assert result[1] == pytest.approx((12.0, -3.0))


def test_barycentric_and_newton_interpolation_recover_cubic() -> None:
    nodes = (-2.0, -0.5, 1.0, 3.0)
    values = tuple(x**3 - 2.0 * x + 1.0 for x in nodes)
    point = 0.25
    expected = point**3 - 2.0 * point + 1.0
    assert barycentric_interpolate(nodes, values, point) == pytest.approx(expected, abs=1e-12)
    coefficients = newton_divided_differences(nodes, values)
    assert newton_interpolate(nodes, coefficients, point) == pytest.approx(expected, abs=1e-12)


def test_piecewise_interpolation_and_chebyshev_nodes_are_explicit() -> None:
    assert piecewise_linear_interpolate((0.0, 1.0), (2.0, 4.0), 0.25) == pytest.approx(2.5)
    assert piecewise_linear_interpolate(
        (0.0, 1.0), (2.0, 4.0), -1.0, extrapolation="clamp"
    ) == pytest.approx(2.0)
    assert piecewise_linear_interpolate(
        (0.0, 1.0), (2.0, 4.0), 2.0, extrapolation="linear"
    ) == pytest.approx(6.0)
    with pytest.raises(MathInvariantError, match="outside|below"):
        piecewise_linear_interpolate((0.0, 1.0), (2.0, 4.0), -1.0)

    nodes = chebyshev_nodes(8, lower=-3.0, upper=5.0)
    assert tuple(sorted(nodes)) == nodes
    assert all(-3.0 < value < 5.0 for value in nodes)
    assert horner((1.0, -2.0, 0.0, 1.0), 2.0) == pytest.approx(5.0)


def test_normal_distribution_oracles_are_mutually_consistent() -> None:
    assert normal_cdf(0.0) == pytest.approx(0.5, abs=1e-15)
    for probability in (0.01, 0.25, 0.5, 0.9, 0.999):
        quantile = normal_quantile(probability)
        assert normal_cdf(quantile) == pytest.approx(probability, abs=3e-15)
    assert math.exp(normal_log_pdf(0.0)) == pytest.approx(1.0 / math.sqrt(2.0 * math.pi))


def test_distribution_log_densities_remain_finite_for_extreme_valid_inputs() -> None:
    assert math.isfinite(student_t_log_pdf(1e6, degrees_of_freedom=3.0, scale=2.0))
    assert math.isfinite(poisson_log_pmf(1000, 1000.0))
    mixture = gaussian_mixture_log_density(
        100.0,
        means=(0.0, 100.0),
        standard_deviations=(1.0, 0.5),
        weights=(1e-300, 1.0),
    )
    assert math.isfinite(mixture)


def test_radix2_fft_matches_dft_and_inverts_exact_reference_signal() -> None:
    values = (1.0, -2.0, 3.0, 0.5, -1.5, 2.5, 0.0, 4.0)
    reference = dft(values)
    fast = fft_radix2(values)
    for left, right in zip(reference, fast):
        assert left.real == pytest.approx(right.real, abs=1e-12)
        assert left.imag == pytest.approx(right.imag, abs=1e-12)
    restored = inverse_fft_radix2(fast)
    for expected, actual in zip(values, restored):
        assert actual.real == pytest.approx(expected, abs=1e-12)
        assert actual.imag == pytest.approx(0.0, abs=1e-12)


def test_convolution_reference_matches_polynomial_product() -> None:
    assert convolution((1.0, 2.0, 3.0), (4.0, 5.0)) == pytest.approx(
        (4.0, 13.0, 22.0, 15.0)
    )


def test_normalized_autocorrelation_has_unit_zero_lag_and_symmetry_signal() -> None:
    values = (1.0, -1.0, 1.0, -1.0)
    result = autocorrelation(values, max_lag=3, normalized=True)
    assert result[0] == pytest.approx(1.0)
    assert result[1] < 0.0
    assert result[2] > 0.0


def test_binary_calibration_report_distinguishes_perfect_and_bad_confidence() -> None:
    perfect = binary_calibration_report(
        (0.0, 0.0, 1.0, 1.0),
        (0, 0, 1, 1),
        bins=4,
    )
    assert perfect.expected_calibration_error == pytest.approx(0.0)
    assert perfect.brier_score == pytest.approx(0.0)

    bad = binary_calibration_report(
        (0.9, 0.9, 0.1, 0.1),
        (0, 0, 1, 1),
        bins=5,
    )
    assert bad.expected_calibration_error == pytest.approx(0.9)
    assert bad.maximum_calibration_error == pytest.approx(0.9)


def test_multiclass_top_label_calibration_uses_full_brier_score() -> None:
    report = top_label_calibration_report(
        ((0.8, 0.1, 0.1), (0.2, 0.7, 0.1)),
        (0, 2),
        bins=5,
    )
    assert report.sample_count == 2
    assert report.expected_calibration_error > 0.0
    assert report.brier_score > 0.0


def test_invalid_sparse_fft_and_distribution_contracts_fail_closed() -> None:
    with pytest.raises(MathInvariantError, match="power of two"):
        fft_radix2((1.0, 2.0, 3.0))
    with pytest.raises(MathInvariantError, match="strictly inside"):
        normal_quantile(1.0)
    with pytest.raises(MathInvariantError, match="strictly increasing"):
        piecewise_linear_interpolate((0.0, 0.0), (1.0, 2.0), 0.0)
