from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    Interval,
    MathInvariantError,
    apply_givens_pair,
    apply_householder_vector,
    beta_binomial_posterior,
    dirichlet_multinomial_posterior,
    givens_rotation,
    householder_reflection,
    interval_hull,
    interval_intersection,
    ldlt_decompose,
    ldlt_solve,
    normal_inverse_gamma_posterior,
    normal_normal_posterior,
)


def test_beta_binomial_and_dirichlet_multinomial_posteriors() -> None:
    beta = beta_binomial_posterior(1.0, 1.0, successes=7, failures=3)
    assert beta.posterior_alpha == pytest.approx(8.0)
    assert beta.posterior_beta == pytest.approx(4.0)
    assert beta.mean == pytest.approx(2.0 / 3.0)
    assert beta.variance > 0.0

    directory = dirichlet_multinomial_posterior((1.0, 1.0, 1.0), (2, 1, 0))
    assert directory.posterior_alpha == pytest.approx((3.0, 2.0, 1.0))
    assert directory.mean == pytest.approx((0.5, 1.0 / 3.0, 1.0 / 6.0))
    assert math.isfinite(directory.log_evidence)


def test_normal_conjugate_posteriors_move_toward_observations() -> None:
    report = normal_normal_posterior(
        0.0,
        4.0,
        (4.0, 5.0, 6.0),
        observation_variance=1.0,
    )
    assert 0.0 < report.posterior_mean < 5.0
    assert report.posterior_variance < report.prior_variance

    nig = normal_inverse_gamma_posterior(
        0.0,
        1.0,
        2.0,
        2.0,
        (4.0, 5.0, 6.0),
    )
    assert nig.kappa == pytest.approx(4.0)
    assert nig.alpha == pytest.approx(3.5)
    assert nig.predictive_scale > 0.0


def test_interval_arithmetic_contains_pointwise_truth() -> None:
    left = Interval(1.0, 2.0)
    right = Interval(3.0, 5.0)
    product = left * right
    assert product.contains(3.0)
    assert product.contains(10.0)
    quotient = right / left
    assert quotient.contains(1.5)
    assert quotient.contains(5.0)

    squared = Interval(-2.0, 3.0).square()
    assert squared.lower == pytest.approx(0.0)
    assert squared.contains(9.0)
    assert Interval(1.0, 4.0).sqrt().contains(2.0)
    assert Interval(1.0, 2.0).exp().contains(math.e)

    hull = interval_hull(left, right)
    assert hull.lower == pytest.approx(1.0)
    assert hull.upper == pytest.approx(5.0)
    intersection = interval_intersection(Interval(0.0, 2.0), Interval(1.0, 3.0))
    assert intersection is not None
    assert intersection.lower == pytest.approx(1.0)
    assert intersection.upper == pytest.approx(2.0)

    with pytest.raises(MathInvariantError, match="contains zero"):
        Interval(-1.0, 1.0).reciprocal()


def test_givens_annihilates_second_component() -> None:
    rotation = givens_rotation(3.0, 4.0)
    first, second = apply_givens_pair(rotation, 3.0, 4.0)
    assert first == pytest.approx(5.0)
    assert second == pytest.approx(0.0, abs=1e-15)
    assert rotation.cosine**2 + rotation.sine**2 == pytest.approx(1.0)


def test_householder_maps_vector_to_first_axis() -> None:
    source = (4.0, 3.0, 0.0)
    reflection = householder_reflection(source)
    transformed = apply_householder_vector(reflection, source)
    assert transformed[0] == pytest.approx(reflection.leading_value, abs=1e-12)
    assert transformed[1:] == pytest.approx((0.0, 0.0), abs=1e-12)


def test_ldlt_reconstructs_indefinite_symmetric_matrix_and_solves() -> None:
    matrix = ((4.0, 2.0, 0.0), (2.0, -2.0, 1.0), (0.0, 1.0, 3.0))
    report = ldlt_decompose(matrix)
    assert report.reconstruction_linf <= 1e-12
    assert report.positive_pivots + report.negative_pivots == 3
    expected = (1.0, -2.0, 0.5)
    rhs = tuple(sum(row[j] * expected[j] for j in range(3)) for row in matrix)
    solution = ldlt_solve(matrix, rhs)
    assert solution == pytest.approx(expected, abs=1e-12)
