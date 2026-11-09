from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    CSRMatrix,
    bicgstab,
    convolution,
    fft_convolution,
    fft_cross_correlation,
    gaussian_process_log_marginal_likelihood,
    gaussian_process_posterior,
    kalman_filter,
    overlap_add_convolution,
    preconditioned_conjugate_gradient,
    rbf_kernel,
    rts_smooth,
)


def test_sparse_pcg_and_bicgstab_recover_known_solutions() -> None:
    spd = CSRMatrix.from_dense(((4.0, 1.0, 0.0), (1.0, 3.0, 1.0), (0.0, 1.0, 2.0)))
    expected = (1.0, -2.0, 3.0)
    rhs = spd.matvec(expected)
    pcg = preconditioned_conjugate_gradient(spd, rhs, tolerance=1e-12)
    assert pcg.converged
    assert pcg.solution == pytest.approx(expected, abs=1e-10)
    assert pcg.residual_l2 <= 1e-10

    nonsymmetric = CSRMatrix.from_dense(((4.0, 1.0, 0.0), (-2.0, 3.0, 1.0), (0.0, 1.0, 2.0)))
    rhs2 = nonsymmetric.matvec(expected)
    bicg = bicgstab(nonsymmetric, rhs2, tolerance=1e-12, max_iterations=50)
    assert bicg.converged
    assert bicg.solution == pytest.approx(expected, abs=1e-9)
    assert bicg.residual_l2 <= 1e-9


def test_fft_and_overlap_add_match_direct_convolution() -> None:
    left = tuple(math.sin(index / 7.0) for index in range(37))
    right = (0.25, -0.5, 1.0, 0.5, -0.125)
    direct = convolution(left, right)
    fast = fft_convolution(left, right)
    blocked = overlap_add_convolution(left, right, block_size=8)
    assert fast == pytest.approx(direct, abs=1e-11)
    assert blocked == pytest.approx(direct, abs=1e-11)

    correlation = fft_cross_correlation((1.0, 2.0, 3.0), (2.0, 1.0))
    assert correlation == pytest.approx((1.0, 4.0, 7.0, 6.0), abs=1e-12)


def test_gaussian_process_interpolates_low_noise_training_values_and_has_finite_evidence() -> None:
    train_x = ((0.0,), (1.0,), (2.0,))
    targets = (0.0, 1.0, 0.0)
    kernel = lambda a, b: rbf_kernel(a, b, gamma=1.5)
    posterior = gaussian_process_posterior(
        train_x,
        targets,
        train_x,
        kernel,
        noise_variance=1e-8,
    )
    assert posterior.mean == pytest.approx(targets, abs=2e-7)
    assert all(value >= -1e-10 for value in posterior.variance)
    assert posterior.minimum_variance >= -1e-10

    evidence = gaussian_process_log_marginal_likelihood(
        train_x,
        targets,
        kernel,
        noise_variance=1e-8,
    )
    assert math.isfinite(evidence.log_marginal_likelihood)
    assert evidence.cholesky_reconstruction_linf <= 1e-12


def test_kalman_filter_and_rts_smoother_reduce_uncertainty() -> None:
    report = kalman_filter(
        ((0.9,), (2.1,), (2.9,), (4.2,)),
        initial_mean=(0.0,),
        initial_covariance=((10.0,),),
        transition=((1.0,),),
        observation=((1.0,),),
        process_covariance=((0.05,),),
        observation_covariance=((0.2,),),
    )
    assert len(report.steps) == 4
    assert report.final_state.covariance[0][0] < 10.0
    assert all(step.innovation_mahalanobis_squared >= 0.0 for step in report.steps)

    smoother = rts_smooth(report, ((1.0,),))
    assert len(smoother.smoothed_states) == 4
    assert smoother.smoothed_states[0].covariance[0][0] <= smoother.filtered_states[0].covariance[0][0] + 1e-12
    assert smoother.smoothed_states[-1].mean == pytest.approx(smoother.filtered_states[-1].mean)
