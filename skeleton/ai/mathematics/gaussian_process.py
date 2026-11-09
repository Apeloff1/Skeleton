"""Gaussian-process regression reference mathematics over canonical kernels."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector, positive_scalar
from .decompositions import cholesky_decompose, solve_cholesky
from .kernels import Kernel
from .linear import dot
from .numerics import compensated_sum


def _samples(name: str, values: Sequence[Sequence[Real]]) -> tuple[Vector, ...]:
    if not values:
        raise MathInvariantError(
            f"{name} must not be empty",
            reason="empty_matrix",
            field=name,
        )
    rows = tuple(finite_vector(f"{name}[{index}]", row) for index, row in enumerate(values))
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise MathInvariantError(
            f"{name} must be rectangular",
            reason="ragged_matrix",
            field=name,
        )
    return rows


def _kernel_value(kernel: Kernel, left: Vector, right: Vector) -> float:
    return finite_scalar("kernel_value", kernel(left, right))


@dataclass(frozen=True, slots=True)
class GaussianProcessPosterior:
    mean: Vector
    covariance: Matrix
    variance: Vector
    training_count: int
    test_count: int
    noise_variance: float
    minimum_variance: float


@dataclass(frozen=True, slots=True)
class GaussianProcessEvidence:
    log_marginal_likelihood: float
    quadratic_term: float
    log_determinant_term: float
    normalization_term: float
    cholesky_reconstruction_linf: float


def gaussian_process_posterior(
    training_inputs: Sequence[Sequence[Real]],
    training_targets: Sequence[Real],
    test_inputs: Sequence[Sequence[Real]],
    kernel: Kernel,
    *,
    noise_variance: Real = 1e-8,
) -> GaussianProcessPosterior:
    train = _samples("training_inputs", training_inputs)
    targets = finite_vector("training_targets", training_targets)
    test = _samples("test_inputs", test_inputs)
    if len(targets) != len(train):
        raise MathInvariantError(
            "GP targets must match training input count",
            reason="dimension_mismatch",
            field="training_targets",
        )
    if len(test[0]) != len(train[0]):
        raise MathInvariantError(
            "GP train/test feature dimensions must match",
            reason="dimension_mismatch",
            field="test_inputs",
        )
    noise = positive_scalar("noise_variance", noise_variance)

    n = len(train)
    m = len(test)
    covariance = tuple(
        tuple(
            _kernel_value(kernel, train[i], train[j]) + (noise if i == j else 0.0)
            for j in range(n)
        )
        for i in range(n)
    )
    alpha = solve_cholesky(covariance, targets)
    cross = tuple(
        tuple(_kernel_value(kernel, train[i], test[j]) for j in range(m))
        for i in range(n)
    )
    means = tuple(
        compensated_sum(cross[i][j] * alpha[i] for i in range(n))
        for j in range(m)
    )
    solved_columns = tuple(
        solve_cholesky(covariance, tuple(cross[i][j] for i in range(n)))
        for j in range(m)
    )
    posterior_covariance = []
    minimum_variance = math.inf
    for i in range(m):
        row = []
        for j in range(m):
            prior = _kernel_value(kernel, test[i], test[j])
            correction = dot(
                tuple(cross[k][i] for k in range(n)),
                solved_columns[j],
            )
            value = prior - correction
            if i == j and value < 0.0 and abs(value) <= 1e-10:
                value = 0.0
            row.append(finite_scalar("posterior_covariance", value))
        posterior_covariance.append(tuple(row))
        minimum_variance = min(minimum_variance, posterior_covariance[-1][i])
    return GaussianProcessPosterior(
        mean=means,
        covariance=tuple(posterior_covariance),
        variance=tuple(posterior_covariance[i][i] for i in range(m)),
        training_count=n,
        test_count=m,
        noise_variance=noise,
        minimum_variance=minimum_variance,
    )


def gaussian_process_log_marginal_likelihood(
    training_inputs: Sequence[Sequence[Real]],
    training_targets: Sequence[Real],
    kernel: Kernel,
    *,
    noise_variance: Real = 1e-8,
) -> GaussianProcessEvidence:
    train = _samples("training_inputs", training_inputs)
    targets = finite_vector("training_targets", training_targets)
    if len(targets) != len(train):
        raise MathInvariantError(
            "GP targets must match training input count",
            reason="dimension_mismatch",
            field="training_targets",
        )
    noise = positive_scalar("noise_variance", noise_variance)
    n = len(train)
    covariance = tuple(
        tuple(
            _kernel_value(kernel, train[i], train[j]) + (noise if i == j else 0.0)
            for j in range(n)
        )
        for i in range(n)
    )
    cholesky = cholesky_decompose(covariance)
    alpha = solve_cholesky(covariance, targets)
    quadratic = -0.5 * dot(targets, alpha)
    log_determinant = -compensated_sum(math.log(cholesky.lower[i][i]) for i in range(n))
    normalization = -0.5 * n * math.log(2.0 * math.pi)
    return GaussianProcessEvidence(
        log_marginal_likelihood=quadratic + log_determinant + normalization,
        quadratic_term=quadratic,
        log_determinant_term=log_determinant,
        normalization_term=normalization,
        cholesky_reconstruction_linf=cholesky.reconstruction_linf,
    )
