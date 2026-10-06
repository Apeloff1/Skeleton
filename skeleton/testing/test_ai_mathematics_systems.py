from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    SplitMix64,
    angular_distance,
    barycentric_triangle,
    binary_cross_entropy,
    bisection_root,
    bracketed_newton_root,
    brier_score,
    combinatorial_laplacian,
    conjugate_gradient,
    cross_entropy_from_logits,
    euclidean_distance,
    graph_quadratic_form,
    halton_point,
    huber_loss,
    label_smoothed_cross_entropy_from_logits,
    mean_absolute_error,
    mean_squared_error,
    monte_carlo_unit_cube,
    normalized_laplacian,
    perplexity,
    project_onto_subspace,
    project_probability_simplex,
    random_walk_matrix,
    stationary_distribution,
    systematic_resample,
)


def test_graph_laplacian_energy_and_normalized_isolated_node() -> None:
    adjacency = (
        (0.0, 1.0, 0.0, 0.0),
        (1.0, 0.0, 2.0, 0.0),
        (0.0, 2.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0),
    )
    laplacian = combinatorial_laplacian(adjacency)
    signal = (1.0, 4.0, -2.0, 10.0)
    assert graph_quadratic_form(laplacian, signal) == pytest.approx(
        (1.0 - 4.0) ** 2 + 2.0 * (4.0 - -2.0) ** 2
    )
    normalized = normalized_laplacian(adjacency)
    assert normalized[3] == pytest.approx((0.0, 0.0, 0.0, 0.0))


def test_random_walk_stationary_distribution_reports_residual() -> None:
    transition = random_walk_matrix(((0.0, 1.0), (1.0, 0.0)))
    report = stationary_distribution(transition)
    assert report.converged
    assert report.probabilities == pytest.approx((0.5, 0.5), abs=1e-15)
    assert report.residual_l1 <= 1e-15


def test_conjugate_gradient_matches_known_spd_solution() -> None:
    report = conjugate_gradient(
        ((4.0, 1.0), (1.0, 3.0)),
        (1.0, 2.0),
    )
    assert report.converged
    assert report.solution == pytest.approx((1.0 / 11.0, 7.0 / 11.0), abs=1e-12)
    assert report.residual_l2 <= 1e-12


def test_conjugate_gradient_rejects_indefinite_matrix() -> None:
    with pytest.raises(MathInvariantError, match="positive definite"):
        conjugate_gradient(((0.0, 1.0), (1.0, 0.0)), (1.0, 0.0))


def test_root_solvers_are_bracketed_and_residual_carrying() -> None:
    bisected = bisection_root(lambda x: x * x - 2.0, 0.0, 2.0)
    assert bisected.converged
    assert bisected.root == pytest.approx(math.sqrt(2.0), abs=2e-12)

    newton = bracketed_newton_root(
        lambda x: x * x - 2.0,
        lambda x: 2.0 * x,
        0.0,
        2.0,
        initial=1.5,
    )
    assert newton.converged
    assert newton.root == pytest.approx(math.sqrt(2.0), abs=1e-12)
    assert newton.newton_steps > 0


def test_splitmix64_and_systematic_resampling_are_reproducible() -> None:
    left = SplitMix64(42)
    right = SplitMix64(42)
    assert [left.next_uint64() for _ in range(8)] == [
        right.next_uint64() for _ in range(8)
    ]
    assert systematic_resample((0.1, 0.2, 0.7), 20, seed=7) == systematic_resample(
        (0.1, 0.2, 0.7), 20, seed=7
    )


def test_halton_and_monte_carlo_reference_sampling() -> None:
    assert halton_point(1, 3) == pytest.approx((0.5, 1.0 / 3.0, 0.2))
    report = monte_carlo_unit_cube(
        lambda point: point[0] * point[0],
        dimensions=1,
        samples=20000,
        seed=123,
    )
    assert report.estimate == pytest.approx(1.0 / 3.0, abs=0.01)
    assert report.standard_error > 0.0


def test_probability_simplex_projection_preserves_mass_and_optimal_shape() -> None:
    projected = project_probability_simplex((0.8, -0.2, 0.7, 4.0), mass=1.0)
    assert all(value >= 0.0 for value in projected)
    assert sum(projected) == pytest.approx(1.0, abs=1e-15)
    assert projected[3] == pytest.approx(1.0)


def test_geometry_reference_metrics_and_subspace_projection() -> None:
    assert euclidean_distance((0.0, 0.0), (3.0, 4.0)) == pytest.approx(5.0)
    assert angular_distance((1.0, 0.0), (0.0, 1.0)) == pytest.approx(math.pi / 2.0)
    barycentric = barycentric_triangle(
        (0.25, 0.25),
        (0.0, 0.0),
        (1.0, 0.0),
        (0.0, 1.0),
    )
    assert barycentric == pytest.approx((0.5, 0.25, 0.25))

    projection = project_onto_subspace(
        (1.0, 2.0, 3.0),
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    )
    assert projection.projection == pytest.approx((1.0, 2.0, 0.0))
    assert projection.residual == pytest.approx((0.0, 0.0, 3.0))
    assert projection.residual_l2 == pytest.approx(3.0)


def test_stable_ai_losses_cover_logits_labels_and_regression() -> None:
    assert mean_squared_error((1.0, 2.0), (2.0, 4.0)) == pytest.approx(2.5)
    assert mean_absolute_error((1.0, 2.0), (2.0, 4.0)) == pytest.approx(1.5)
    assert huber_loss((0.0,), (3.0,), delta=1.0) == pytest.approx(2.5)
    assert binary_cross_entropy((1.0, 0.0), (0.8, 0.25)) == pytest.approx(
        (-math.log(0.8) - math.log(0.75)) / 2.0
    )

    logits = (1000.0, 999.0, 998.0)
    loss = cross_entropy_from_logits(logits, 0)
    expected = math.log(1.0 + math.exp(-1.0) + math.exp(-2.0))
    assert loss == pytest.approx(expected, abs=1e-12)
    smooth = label_smoothed_cross_entropy_from_logits(logits, 0, smoothing=0.1)
    assert smooth > loss
    assert brier_score((0.7, 0.2, 0.1), 0) == pytest.approx(0.14)
    assert perplexity(math.log(10.0)) == pytest.approx(10.0)


def test_loss_and_graph_support_violations_fail_closed() -> None:
    with pytest.raises(MathInvariantError, match="zero predicted support"):
        binary_cross_entropy((1.0,), (0.0,))
    with pytest.raises(MathInvariantError, match="symmetric"):
        combinatorial_laplacian(((0.0, 1.0), (0.5, 0.0)))
